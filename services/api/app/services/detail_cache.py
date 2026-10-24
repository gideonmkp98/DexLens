import asyncio
import logging
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    details: dict[str, Any]
    fetched_at: datetime


@dataclass
class DetailLookupResult:
    status: str  # "available", "stale", "unavailable"
    source: str
    fetched_at: datetime | None
    details: dict[str, Any] | None


class DetailCache:
    """In-memory bounded LRU cache for card details.

    Features:
    - Bounded entries with LRU eviction.
    - Configurable fresh TTL (default 6h) and stale fallback (up to 24h).
    - Failed lookup cooldown to avoid hammering the provider.
    - Deduplication of concurrent fetches for the same card key without global lock.
    """

    def __init__(
        self,
        max_entries: int | None = None,
        fresh_ttl_seconds: int | None = None,
        max_stale_seconds: int | None = None,
        failed_cooldown_seconds: int | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.max_entries = (
            max_entries
            if max_entries is not None
            else settings.DETAIL_CACHE_MAX_ENTRIES
        )
        self.fresh_ttl_seconds = (
            fresh_ttl_seconds
            if fresh_ttl_seconds is not None
            else settings.DETAIL_CACHE_TTL_SECONDS
        )
        self.max_stale_seconds = (
            max_stale_seconds
            if max_stale_seconds is not None
            else settings.DETAIL_CACHE_MAX_STALE_SECONDS
        )
        self.failed_cooldown_seconds = (
            failed_cooldown_seconds
            if failed_cooldown_seconds is not None
            else settings.DETAIL_CACHE_FAILED_COOLDOWN_SECONDS
        )
        self._clock = clock or (lambda: datetime.now(UTC))

        self._store: OrderedDict[tuple[str, str, str], CacheEntry] = OrderedDict()
        self._failed_cooldowns: dict[tuple[str, str, str], float] = {}
        self._in_flight: dict[tuple[str, str, str], asyncio.Future[Any]] = {}
        self._lock = asyncio.Lock()

    def _now(self) -> datetime:
        return self._clock()

    def _is_failed_cooldown_active(self, key: tuple[str, str, str]) -> bool:
        if key in self._failed_cooldowns:
            cooldown_expiry = self._failed_cooldowns[key]
            if time.monotonic() < cooldown_expiry:
                return True
            del self._failed_cooldowns[key]
        return False

    def _set_failed_cooldown(self, key: tuple[str, str, str]) -> None:
        self._failed_cooldowns[key] = time.monotonic() + self.failed_cooldown_seconds

    def _get_entry(self, key: tuple[str, str, str]) -> CacheEntry | None:
        if key in self._store:
            entry = self._store[key]
            self._store.move_to_end(key)
            return entry
        return None

    def _put_entry(
        self, key: tuple[str, str, str], details: dict[str, Any], fetched_at: datetime
    ) -> None:
        if key in self._store:
            self._store.move_to_end(key)
            self._store[key] = CacheEntry(details=details, fetched_at=fetched_at)
        else:
            if len(self._store) >= self.max_entries:
                self._store.popitem(last=False)
            self._store[key] = CacheEntry(details=details, fetched_at=fetched_at)

        # Clear any failed cooldown if fetch succeeded
        self._failed_cooldowns.pop(key, None)

    async def get_or_fetch(
        self,
        source: str,
        language: str,
        external_id: str,
        fetcher: Callable[[], Any],
    ) -> DetailLookupResult:
        key = (source, language, external_id)
        now = self._now()

        # 1. Quick check: do we have a fresh cached item?
        entry = self._get_entry(key)
        if entry:
            age_seconds = (now - entry.fetched_at).total_seconds()
            if age_seconds <= self.fresh_ttl_seconds:
                return DetailLookupResult(
                    status="available",
                    source=source,
                    fetched_at=entry.fetched_at,
                    details=entry.details,
                )

        # 2. Check failed lookup cooldown
        if self._is_failed_cooldown_active(key):
            # If we have an eligible stale entry, return it
            if entry:
                age_seconds = (now - entry.fetched_at).total_seconds()
                if age_seconds <= self.max_stale_seconds:
                    return DetailLookupResult(
                        status="stale",
                        source=source,
                        fetched_at=entry.fetched_at,
                        details=entry.details,
                    )
            return DetailLookupResult(
                status="unavailable",
                source=source,
                fetched_at=None,
                details=None,
            )

        # 3. Deduplicate concurrent fetches using Future per key
        fetch_leader = False
        async with self._lock:
            if key in self._in_flight:
                future = self._in_flight[key]
            else:
                loop = asyncio.get_running_loop()
                future = loop.create_future()
                self._in_flight[key] = future
                fetch_leader = True

        if not fetch_leader:
            # Another task is currently fetching this exact card
            try:
                await future
            except Exception:
                pass  # Fall through to check cache/stale below
            fresh_entry = self._get_entry(key)
            if fresh_entry:
                age = (self._now() - fresh_entry.fetched_at).total_seconds()
                if age <= self.fresh_ttl_seconds:
                    return DetailLookupResult(
                        status="available",
                        source=source,
                        fetched_at=fresh_entry.fetched_at,
                        details=fresh_entry.details,
                    )
                if age <= self.max_stale_seconds:
                    return DetailLookupResult(
                        status="stale",
                        source=source,
                        fetched_at=fresh_entry.fetched_at,
                        details=fresh_entry.details,
                    )
            return DetailLookupResult(
                status="unavailable",
                source=source,
                fetched_at=None,
                details=None,
            )

        # 4. Fetch leader performs network call
        try:
            fetched_data = await fetcher()
            if fetched_data:
                fetch_time = self._now()
                self._put_entry(key, fetched_data, fetch_time)
                future.set_result(fetched_data)
                return DetailLookupResult(
                    status="available",
                    source=source,
                    fetched_at=fetch_time,
                    details=fetched_data,
                )
            else:
                # Provider returned 404 or empty
                self._set_failed_cooldown(key)
                future.set_result(None)
                if entry:
                    age_seconds = (now - entry.fetched_at).total_seconds()
                    if age_seconds <= self.max_stale_seconds:
                        return DetailLookupResult(
                            status="stale",
                            source=source,
                            fetched_at=entry.fetched_at,
                            details=entry.details,
                        )
                return DetailLookupResult(
                    status="unavailable",
                    source=source,
                    fetched_at=None,
                    details=None,
                )
        except Exception as err:
            logger.warning(
                "Error fetching card details for %s from provider: %s", key, err
            )
            self._set_failed_cooldown(key)
            if not future.done():
                future.set_exception(err)

            # Fallback to bounded stale data if available
            if entry:
                age_seconds = (now - entry.fetched_at).total_seconds()
                if age_seconds <= self.max_stale_seconds:
                    return DetailLookupResult(
                        status="stale",
                        source=source,
                        fetched_at=entry.fetched_at,
                        details=entry.details,
                    )

            return DetailLookupResult(
                status="unavailable",
                source=source,
                fetched_at=None,
                details=None,
            )
        finally:
            async with self._lock:
                self._in_flight.pop(key, None)


# Global process-level detail cache instance
detail_cache = DetailCache()


def map_card_details(raw: dict[str, Any]) -> dict[str, Any]:
    """Map raw TCGdex card details to a clean, allowlisted subset.

    Explicitly excludes prices and marketplace data.
    Preserves unknown or absent data as unknown.
    """
    details: dict[str, Any] = {}

    allowed_keys = [
        "category",
        "illustrator",
        "rarity",
        "hp",
        "types",
        "regulationMark",
    ]
    for k in allowed_keys:
        if k in raw and raw[k] is not None:
            details[k] = raw[k]

    if "variants" in raw and isinstance(raw["variants"], dict):
        details["variants"] = raw["variants"]

    if "attacks" in raw and isinstance(raw["attacks"], list):
        clean_attacks = []
        for att in raw["attacks"]:
            if isinstance(att, dict):
                clean_att = {
                    "name": att.get("name"),
                    "cost": att.get("cost"),
                    "damage": att.get("damage"),
                    "effect": att.get("effect"),
                }
                clean_attacks.append(
                    {k: v for k, v in clean_att.items() if v is not None}
                )
        if clean_attacks:
            details["attacks"] = clean_attacks

    if "abilities" in raw and isinstance(raw["abilities"], list):
        clean_abilities = []
        for ab in raw["abilities"]:
            if isinstance(ab, dict):
                clean_ab = {
                    "type": ab.get("type"),
                    "name": ab.get("name"),
                    "effect": ab.get("effect"),
                }
                clean_abilities.append(
                    {k: v for k, v in clean_ab.items() if v is not None}
                )
        if clean_abilities:
            details["abilities"] = clean_abilities

    return details
