"""Bounded read-through cache for recognition's on-demand provider requests."""

import json
from typing import Any

from app.services.detail_cache import DetailCache
from app.services.tcgdex import TcgdexClient, TcgdexConnectionError

recognition_cache = DetailCache(max_entries=256)


class CachedRecognitionCatalog:
    def __init__(self, client: TcgdexClient, cache: DetailCache):
        self.client = client
        self.cache = cache

    async def _read(self, method: str, *args: Any, **kwargs: Any) -> Any:
        key = json.dumps([args, kwargs], sort_keys=True)
        result = await self.cache.get_or_fetch(
            resource=f"recognition:{method}",
            source=self.client.base_url,
            language="en",
            external_id=key,
            fetcher=lambda: getattr(self.client, method)(*args, **kwargs),
        )
        if result.status == "unavailable" and result.error:
            raise TcgdexConnectionError(
                "Recognition catalog temporarily unavailable"
            ) from result.error
        return result.details

    async def get_sets(self) -> list[dict[str, Any]]:
        return await self._read("get_sets") or []

    async def get_set(self, set_id: str) -> dict[str, Any] | None:
        return await self._read("get_set", set_id)

    async def get_card(self, card_id: str) -> dict[str, Any] | None:
        return await self._read("get_card", card_id)

    async def get_cards_search(self, **kwargs: Any) -> list[dict[str, Any]]:
        return await self._read("get_cards_search", **kwargs) or []
