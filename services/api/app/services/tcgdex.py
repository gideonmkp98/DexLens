import asyncio
import urllib.parse
from typing import Any

import httpx

from app.core.config import settings


class TcgdexError(Exception):
    """Base exception for TCGdex API client errors."""


class TcgdexNotFoundError(TcgdexError):
    """Raised when a set or card resource is not found on TCGdex."""


class TcgdexRateLimitError(TcgdexError):
    """Raised when rate limits are exceeded."""


class TcgdexConnectionError(TcgdexError):
    """Raised on connection failures or timeouts after retries."""


class TcgdexInvalidLanguageError(TcgdexError):
    """Raised when an unsupported language is requested."""


def is_digital_set(set_data: dict[str, Any]) -> bool:
    """Determine whether a set is a digital-only product (e.g., Pokémon TCG Pocket).

    Digital products are identified by:
    1. Series ID equals 'tcgp' or series name is 'Pokémon TCG Pocket'
    2. Logo or symbol URL path containing '/tcgp/'
    3. Set ID or name containing 'pocket'
    """
    serie = set_data.get("serie")
    if isinstance(serie, dict):
        serie_id = str(serie.get("id", "")).lower()
        serie_name = str(serie.get("name", "")).lower()
        if serie_id == "tcgp" or "pocket" in serie_name:
            return True

    logo = str(set_data.get("logo", "")).lower()
    symbol = str(set_data.get("symbol", "")).lower()
    if "/tcgp/" in logo or "/tcgp/" in symbol:
        return True

    set_id = str(set_data.get("id", "")).lower()
    if set_id.startswith("tcgp") or "pocket" in set_id:
        return True

    set_name = str(set_data.get("name", "")).lower()
    if "pocket" in set_name:
        return True

    return False


def is_digital_card(card_data: dict[str, Any]) -> bool:
    """Determine whether a card belongs to a digital-only product."""
    card_id = str(card_data.get("id", "")).lower()
    if card_id.startswith("tcgp") or "pocket" in card_id:
        return True

    image = str(card_data.get("image", "")).lower()
    if "/tcgp/" in image:
        return True

    set_obj = card_data.get("set")
    if isinstance(set_obj, dict):
        if is_digital_set(set_obj):
            return True

    return False


class TcgdexClient:
    """Async HTTP client for interacting with the TCGdex REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float | None = None,
        max_retries: int | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = (base_url or settings.TCGDEX_BASE_URL).rstrip("/")
        self.timeout = timeout if timeout is not None else settings.TCGDEX_HTTP_TIMEOUT
        self.max_retries = (
            max_retries if max_retries is not None else settings.IMPORT_MAX_RETRIES
        )
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            timeout=self.timeout,
            headers={
                "Accept": "application/json",
                "User-Agent": "Pokemon-TCG-Scanner/0.2.0",
            },
        )

    async def __aenter__(self) -> "TcgdexClient":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    def _validate_language(self, language: str) -> None:
        if language not in settings.SUPPORTED_LANGUAGES:
            raise TcgdexInvalidLanguageError(
                f"Language '{language}' is not supported. "
                f"Supported: {settings.SUPPORTED_LANGUAGES}"
            )

    async def _request(
        self,
        endpoint: str,
        language: str = "en",
        params: dict[str, Any] | None = None,
    ) -> Any:
        self._validate_language(language)
        quoted_lang = urllib.parse.quote(language, safe="")
        clean_ep = endpoint.lstrip("/")
        url = f"{self.base_url}/{quoted_lang}/{clean_ep}"

        attempts = 0
        backoff = settings.IMPORT_RETRY_BACKOFF

        while attempts <= self.max_retries:
            attempts += 1
            try:
                response = await self._client.get(url, params=params)

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 404:
                    return None

                if response.status_code == 429:
                    retry_after_header = response.headers.get("Retry-After")
                    sleep_time = backoff
                    if retry_after_header and retry_after_header.isdigit():
                        sleep_time = min(float(retry_after_header), 10.0)

                    if attempts > self.max_retries:
                        raise TcgdexRateLimitError(
                            f"TCGdex rate limit exceeded at {url} "
                            f"after {attempts} attempts"
                        )
                    await asyncio.sleep(sleep_time)
                    backoff *= 2
                    continue

                if 500 <= response.status_code < 600:
                    if attempts > self.max_retries:
                        raise TcgdexConnectionError(
                            f"TCGdex server error {response.status_code} at {url}"
                        )
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue

                # Permanent client errors (400, 401, 403, etc.)
                preview = response.text[:200]
                raise TcgdexError(
                    f"TCGdex returned HTTP {response.status_code} for {url}: {preview}"
                )

            except (httpx.TimeoutException, httpx.NetworkError) as err:
                if attempts > self.max_retries:
                    raise TcgdexConnectionError(
                        f"Network failure connecting to TCGdex at {url}: {err}"
                    ) from err
                await asyncio.sleep(backoff)
                backoff *= 2

    async def get_sets(self, language: str = "en") -> list[dict[str, Any]]:
        """Fetch all set summaries for a given language."""
        data = await self._request("sets", language=language)
        if data is None or not isinstance(data, list):
            return []
        return data

    async def get_set(self, set_id: str, language: str = "en") -> dict[str, Any] | None:
        """Fetch detailed set metadata including card summaries."""
        safe_id = urllib.parse.quote(set_id, safe="")
        data = await self._request(f"sets/{safe_id}", language=language)
        if data is None or not isinstance(data, dict):
            return None
        return data

    async def get_card(
        self, card_id: str, language: str = "en"
    ) -> dict[str, Any] | None:
        """Fetch full details for an individual card."""
        safe_id = urllib.parse.quote(card_id, safe="")
        data = await self._request(f"cards/{safe_id}", language=language)
        if data is None or not isinstance(data, dict):
            return None
        return data

    async def get_cards_search(
        self,
        name: str | None = None,
        local_id: str | None = None,
        page: int | None = 1,
        page_size: int = 24,
        language: str = "en",
    ) -> list[dict[str, Any]]:
        """Search summaries; page=None retrieves all matching summaries."""
        params: dict[str, Any] = {}
        if page is not None:
            params.update(
                {
                    "pagination:page": page,
                    "pagination:itemsPerPage": page_size,
                }
            )
        if name:
            params["name"] = name
        if local_id:
            params["localId"] = local_id

        data = await self._request("cards", language=language, params=params)
        if data is None:
            return []
        if not isinstance(data, list) or any(not isinstance(c, dict) for c in data):
            raise TcgdexError("Invalid card search response from TCGdex")
        return data
