import asyncio
import json
import logging
import urllib.error
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

import dacite
from tcgdexsdk import Card, CardResume, Query, TCGdex
from tcgdexsdk.enums import Extension, Quality

from app.core.config import settings
from app.integrations.tcgdex.exceptions import (
    TcgdexConnectionError,
    TcgdexError,
    TcgdexInvalidLanguageError,
    TcgdexNotFoundError,
    TcgdexRateLimitError,
)
from app.integrations.tcgdex.mapper import (
    derive_image_urls,
    map_tcgdex_card,
    map_tcgdex_card_resume,
    map_tcgdex_set,
    map_tcgdex_set_resume,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TCGdexProvider:
    """Provider responsible for interacting with the official TCGdex Python SDK."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        backoff: float | None = None,
        sdk: Any | None = None,
        client: Any | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or getattr(settings, "TCGDEX_BASE_URL", "https://api.tcgdex.net/v2")
        ).rstrip("/")
        self.timeout = (
            timeout
            if timeout is not None
            else getattr(settings, "TCGDEX_HTTP_TIMEOUT", 10.0)
        )
        self.max_retries = (
            max_retries
            if max_retries is not None
            else getattr(settings, "IMPORT_MAX_RETRIES", 3)
        )
        self.backoff = (
            backoff
            if backoff is not None
            else getattr(settings, "IMPORT_RETRY_BACKOFF", 1.0)
        )

        # Allow passing mock SDK or client for unit testing
        self._custom_sdk = sdk or client
        self._sdks: dict[str, Any] = {}
        if self._custom_sdk is not None:
            self._sdks["en"] = self._custom_sdk

    async def __aenter__(self) -> "TCGdexProvider":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close provider resources."""
        self._sdks.clear()

    def _validate_language(self, language: str) -> str:
        clean_lang = language.lower().strip()
        supported = getattr(settings, "SUPPORTED_LANGUAGES", ["en"])
        if clean_lang not in supported:
            raise TcgdexInvalidLanguageError(
                f"Language '{language}' is not supported. Supported: {supported}"
            )
        return clean_lang

    def _get_sdk(self, language: str = "en") -> Any:
        clean_lang = self._validate_language(language)
        if self._custom_sdk is not None:
            return self._custom_sdk

        if clean_lang not in self._sdks:
            sdk_instance = TCGdex(clean_lang)
            if self.base_url and hasattr(sdk_instance, "setEndpoint"):
                sdk_instance.setEndpoint(self.base_url)
            self._sdks[clean_lang] = sdk_instance

        return self._sdks[clean_lang]

    async def _execute_with_retry(
        self,
        operation: Callable[[], Coroutine[Any, Any, T]],
        operation_name: str = "TCGdex request",
    ) -> T:
        attempts = 0
        current_backoff = self.backoff

        while attempts <= self.max_retries:
            attempts += 1
            try:
                return await operation()
            except urllib.error.HTTPError as err:
                if err.code == 404:
                    raise TcgdexNotFoundError(f"Resource not found: {err}") from err
                if err.code == 429:
                    if attempts > self.max_retries:
                        raise TcgdexRateLimitError(
                            f"Rate limit exceeded after {attempts} attempts"
                        ) from err
                    retry_header = (
                        getattr(err.headers, "get", lambda _: None)("Retry-After")
                        if hasattr(err, "headers")
                        else None
                    )
                    sleep_time = (
                        min(float(retry_header), 10.0)
                        if retry_header and retry_header.isdigit()
                        else current_backoff
                    )
                    await asyncio.sleep(sleep_time)
                    current_backoff *= 2
                    continue
                if 500 <= err.code < 600:
                    if attempts > self.max_retries:
                        raise TcgdexConnectionError(
                            f"TCGdex server error {err.code}: {err}"
                        ) from err
                    await asyncio.sleep(current_backoff)
                    current_backoff *= 2
                    continue
                raise TcgdexError(f"TCGdex HTTP error {err.code}: {err}") from err
            except (
                urllib.error.URLError,
                TimeoutError,
                ConnectionError,
                OSError,
            ) as err:
                if attempts > self.max_retries:
                    raise TcgdexConnectionError(
                        f"Network failure connecting to TCGdex during "
                        f"{operation_name}: {err}"
                    ) from err
                await asyncio.sleep(current_backoff)
                current_backoff *= 2
            except (
                json.JSONDecodeError,
                dacite.DaciteError,
                TypeError,
                ValueError,
            ) as err:
                raise TcgdexError(
                    f"Malformed or unexpected response from TCGdex: {err}"
                ) from err
            except TcgdexError:
                raise
            except Exception as err:
                raise TcgdexError(
                    f"Unexpected error communicating with TCGdex: {err}"
                ) from err

        raise TcgdexConnectionError(f"Max retries exceeded for {operation_name}")

    async def get_card(
        self,
        card_id: str,
        language: str = "en",
    ) -> dict[str, Any] | None:
        """Fetch full details for an individual card."""
        sdk = self._get_sdk(language)
        try:
            card = await self._execute_with_retry(
                lambda: sdk.card.get(card_id),
                operation_name=f"get_card({card_id})",
            )
        except TcgdexNotFoundError:
            return None

        if card is None:
            return None
        return map_tcgdex_card(card)

    async def search_cards(
        self,
        name: str | None = None,
        local_id: str | None = None,
        page: int | None = 1,
        page_size: int = 24,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Search card summaries using official TCGdex SDK Query."""
        sdk = self._get_sdk(language)
        query: Query | None = None
        if name or local_id or page is not None:
            query = Query()
            if name:
                query.contains("name", name)
            if local_id:
                query.contains("localId", local_id)
            if page is not None:
                query.paginate(page, page_size)

        try:
            cards = await self._execute_with_retry(
                lambda: sdk.card.list(query),
                operation_name=f"search_cards(name={name}, local_id={local_id})",
            )
        except TcgdexNotFoundError:
            return []

        if cards is None or not isinstance(cards, list):
            return []

        return [map_tcgdex_card_resume(c) for c in cards]

    # Backward compatibility alias
    get_cards_search = search_cards

    async def get_set(
        self,
        set_id: str,
        language: str = "en",
    ) -> dict[str, Any] | None:
        """Fetch detailed set metadata including card summaries."""
        sdk = self._get_sdk(language)
        try:
            set_obj = await self._execute_with_retry(
                lambda: sdk.set.get(set_id),
                operation_name=f"get_set({set_id})",
            )
        except TcgdexNotFoundError:
            return None

        if set_obj is None:
            return None
        return map_tcgdex_set(set_obj)

    async def get_sets(
        self,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Fetch all set summaries for a given language."""
        sdk = self._get_sdk(language)
        try:
            sets = await self._execute_with_retry(
                lambda: sdk.set.list(),
                operation_name="get_sets",
            )
        except TcgdexNotFoundError:
            return []

        if sets is None or not isinstance(sets, list):
            return []

        return [map_tcgdex_set_resume(s) for s in sets]

    def get_card_image_url(
        self,
        card: Any,
        quality: str = "high",
        extension: str = "webp",
    ) -> str | None:
        """Obtain card image URL using SDK helpers."""
        if isinstance(card, (Card, CardResume)):
            qual_enum = Quality.HIGH if quality.lower() == "high" else Quality.LOW
            ext_enum = (
                Extension.WEBP
                if extension.lower() == "webp"
                else (Extension.PNG if extension.lower() == "png" else Extension.JPG)
            )
            return card.get_image_url(qual_enum, ext_enum)

        low_url, high_url = derive_image_urls(card)
        return high_url if quality.lower() == "high" else low_url
