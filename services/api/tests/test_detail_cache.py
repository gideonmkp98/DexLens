import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.cards import get_tcgdex_client
from app.main import app
from app.models.card import Card
from app.models.set import Set
from app.services.detail_cache import DetailCache, map_card_details
from app.services.tcgdex import TcgdexClient


@pytest.mark.asyncio
async def test_cache_miss_fetches_and_populates_cache():
    cache = DetailCache(fresh_ttl_seconds=100, max_stale_seconds=500)
    fetcher = AsyncMock(return_value={"rarity": "Rare", "hp": 100})

    res = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res.status == "available"
    assert res.details == {"rarity": "Rare", "hp": 100}
    assert fetcher.call_count == 1

    # Second call (hit) avoids provider call
    res2 = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res2.status == "available"
    assert fetcher.call_count == 1  # Still 1!


@pytest.mark.asyncio
async def test_expired_cache_refreshes_after_ttl():
    current_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    cache = DetailCache(
        fresh_ttl_seconds=3600,
        max_stale_seconds=86400,
        clock=lambda: current_time,
    )

    fetcher = AsyncMock(
        side_effect=[
            {"hp": 60},
            {"hp": 70},
        ]
    )

    # Initial fetch
    res1 = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res1.details == {"hp": 60}
    assert fetcher.call_count == 1

    # Advance time beyond fresh TTL (2 hours later)
    current_time += timedelta(hours=2)

    res2 = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res2.status == "available"
    assert res2.details == {"hp": 70}
    assert fetcher.call_count == 2


@pytest.mark.asyncio
async def test_refresh_failure_uses_eligible_stale_data():
    current_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    cache = DetailCache(
        fresh_ttl_seconds=3600,
        max_stale_seconds=86400,
        failed_cooldown_seconds=10,
        clock=lambda: current_time,
    )

    fetcher = AsyncMock()
    fetcher.side_effect = [
        {"hp": 60},  # Initial success
        Exception("Provider unavailable"),  # Refresh failure
    ]

    # Initial success
    res1 = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res1.status == "available"
    initial_fetched_at = res1.fetched_at

    # Advance past fresh TTL (4 hours later)
    current_time += timedelta(hours=4)

    # Refresh fails -> returns stale data
    res2 = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res2.status == "stale"
    assert res2.details == {"hp": 60}
    assert res2.fetched_at == initial_fetched_at  # Fetched_at NOT extended


@pytest.mark.asyncio
async def test_stale_data_not_served_beyond_max_stale_age():
    current_time = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    cache = DetailCache(
        fresh_ttl_seconds=3600,
        max_stale_seconds=86400,  # 24 hours
        failed_cooldown_seconds=10,
        clock=lambda: current_time,
    )

    fetcher = AsyncMock(
        side_effect=[
            {"hp": 60},
            Exception("Provider dead"),
        ]
    )

    await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)

    # Advance time 25 hours later (exceeding 24h max stale)
    current_time += timedelta(hours=25)

    res = await cache.get_or_fetch("tcgdex", "en", "card-1", fetcher)
    assert res.status == "unavailable"
    assert res.details is None


@pytest.mark.asyncio
async def test_cache_size_bound_lru_eviction():
    cache = DetailCache(max_entries=2, fresh_ttl_seconds=3600)
    fetcher = AsyncMock(side_effect=lambda: {"dummy": True})

    await cache.get_or_fetch("tcgdex", "en", "c1", fetcher)
    await cache.get_or_fetch("tcgdex", "en", "c2", fetcher)
    assert len(cache._store) == 2

    # Adding c3 evicts c1 (the least recently used)
    await cache.get_or_fetch("tcgdex", "en", "c3", fetcher)
    assert len(cache._store) == 2
    assert ("tcgdex", "en", "c1") not in cache._store
    assert ("tcgdex", "en", "c2") in cache._store
    assert ("tcgdex", "en", "c3") in cache._store


@pytest.mark.asyncio
async def test_failed_lookup_cooldown():
    cache = DetailCache(failed_cooldown_seconds=60)
    fetcher = AsyncMock(side_effect=Exception("Timeout"))

    res1 = await cache.get_or_fetch("tcgdex", "en", "bad-card", fetcher)
    assert res1.status == "unavailable"
    assert fetcher.call_count == 1

    # Second immediate call uses cooldown, avoids calling fetcher
    res2 = await cache.get_or_fetch("tcgdex", "en", "bad-card", fetcher)
    assert res2.status == "unavailable"
    assert fetcher.call_count == 1  # Did not call again!


@pytest.mark.asyncio
async def test_concurrent_requests_deduplicated():
    cache = DetailCache(fresh_ttl_seconds=100)

    call_count = 0

    async def slow_fetcher():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"hp": 120}

    # Launch 5 concurrent calls for the exact same card
    results = await asyncio.gather(
        *[
            cache.get_or_fetch("tcgdex", "en", "shared-card", slow_fetcher)
            for _ in range(5)
        ]
    )

    assert call_count == 1  # Only ONE network fetch executed!
    assert all(r.status == "available" for r in results)
    assert all(r.details == {"hp": 120} for r in results)


def test_map_card_details_excludes_pricing(sample_card_detail_fixture):
    mapped = map_card_details(sample_card_detail_fixture)

    # Allowed fields are present
    assert mapped["category"] == "Pokemon"
    assert mapped["illustrator"] == "Ken Sugimori"
    assert mapped["rarity"] == "Rare Holo"
    assert mapped["hp"] == 80
    assert mapped["types"] == ["Psychic"]
    assert mapped["variants"]["holo"] is True
    assert len(mapped["attacks"]) == 1
    assert len(mapped["abilities"]) == 1

    # Pricing and marketplace fields are strictly excluded
    assert "pricing" not in mapped
    assert "cardmarket" not in mapped
    assert "tcgplayer" not in mapped


def test_card_details_api_unknown_card_returns_404(client: TestClient):
    mock_client = AsyncMock(spec=TcgdexClient)
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    try:
        res = client.get("/api/v1/cards/999999/details")
        assert res.status_code == 404
        assert mock_client.get_card.call_count == 0  # No provider call!
    finally:
        app.dependency_overrides.pop(get_tcgdex_client, None)


def test_card_details_api_success_enrichment(
    client: TestClient, db: Session, sample_card_detail_fixture
):
    s = Set(
        source="tcgdex",
        external_id="base1",
        name="Base Set",
        language="en",
    )
    db.add(s)
    db.flush()

    c = Card(
        source="tcgdex",
        external_id="base1-1",
        set_id=s.id,
        local_id="1",
        name="Alakazam",
        language="en",
    )
    db.add(c)
    db.commit()

    mock_client = AsyncMock(spec=TcgdexClient)
    mock_client.get_card.return_value = sample_card_detail_fixture
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    try:
        res = client.get(f"/api/v1/cards/{c.id}/details")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "available"
        assert data["source"] == "tcgdex"
        assert data["details"]["category"] == "Pokemon"
        assert data["details"]["rarity"] == "Rare Holo"
        assert "pricing" not in data["details"]
    finally:
        app.dependency_overrides.pop(get_tcgdex_client, None)
