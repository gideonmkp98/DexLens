from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.cards import get_tcgdex_client, search_cache
from app.main import app
from app.services.detail_cache import CacheEntry, catalog_cache
from app.services.tcgdex import TcgdexClient, TcgdexConnectionError


@pytest.fixture(autouse=True)
def clear_catalog_cache():
    search_cache._store.clear()
    search_cache._failed_cooldowns.clear()
    search_cache._failed_errors.clear()
    search_cache._in_flight.clear()
    catalog_cache._store.clear()
    catalog_cache._failed_cooldowns.clear()
    catalog_cache._failed_errors.clear()
    catalog_cache._in_flight.clear()
    yield
    catalog_cache._store.clear()
    catalog_cache._failed_cooldowns.clear()
    catalog_cache._failed_errors.clear()
    catalog_cache._in_flight.clear()


@pytest.fixture
def mock_tcgdex():
    mock_client = AsyncMock(spec=TcgdexClient)
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client
    yield mock_client
    app.dependency_overrides.pop(get_tcgdex_client, None)


def test_list_cards_with_set_id_in_memory_filter(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
):
    """Verify card filtering by name and local number within a set from cache."""
    mock_tcgdex.get_set.return_value = sample_set_fixture

    # 1. Filter by set_id only (5 cards in sample_set_fixture)
    res = client.get("/api/v1/cards?set_id=base1")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    assert all(c["set_id"] == "base1" for c in data["items"])
    assert all(c["set_name"] == "Base Set" for c in data["items"])
    mock_tcgdex.get_set.assert_awaited_once_with("base1", language="en")

    # 2. In-memory filter by name (partial case-insensitive)
    mock_tcgdex.get_set.reset_mock()
    res_name = client.get("/api/v1/cards?set_id=base1&name=pika")
    assert res_name.status_code == 200
    data_name = res_name.json()
    assert data_name["total"] == 1
    assert data_name["items"][0]["name"] == "Pikachu"
    assert data_name["items"][0]["local_id"] == "TG01"

    # 3. In-memory filter by local number (exact match)
    res_num = client.get("/api/v1/cards?set_id=base1&number=1")
    assert res_num.status_code == 200
    data_num = res_num.json()
    assert data_num["total"] == 1
    assert data_num["items"][0]["name"] == "Alakazam"
    assert data_num["items"][0]["local_id"] == "1"

    # 4. Filter with no match returns empty list
    res_empty = client.get("/api/v1/cards?set_id=base1&name=mewtwo")
    assert res_empty.status_code == 200
    data_empty = res_empty.json()
    assert data_empty["total"] == 0
    assert len(data_empty["items"]) == 0


def test_list_cards_global_search(client: TestClient, mock_tcgdex: AsyncMock):
    """Verify global card search without set_id calls get_cards_search."""
    mock_results = [
        {
            "id": "base1-58",
            "localId": "58",
            "name": "Pikachu",
            "image": "https://assets.tcgdex.net/en/base/base1/58",
            "set": {"id": "base1", "name": "Base Set"},
        },
        {
            "id": "base2-60",
            "localId": "60",
            "name": "Pikachu",
            "image": "https://assets.tcgdex.net/en/base/base2/60",
            "set": {"id": "base2", "name": "Jungle"},
        },
    ]
    mock_tcgdex.get_cards_search.return_value = mock_results

    res = client.get("/api/v1/cards?name=pikachu")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["page"] == 1
    assert data["page_size"] == 24
    assert data["has_more"] is False
    assert data["items"][0]["name"] == "Pikachu"
    assert data["items"][0]["set_name"] == "Base Set"
    assert data["items"][1]["set_name"] == "Jungle"
    assert (
        data["items"][0]["small_image_url"]
        == "https://assets.tcgdex.net/en/base/base1/58/low.webp"
    )

    mock_tcgdex.get_cards_search.assert_awaited_once_with(
        name="pikachu",
        local_id=None,
        page=None,
        language="en",
    )


@pytest.mark.parametrize(
    ("page", "result_count", "expected_has_more"),
    [(1, 24, True), (2, 24, True), (3, 5, False), (4, 0, False)],
)
def test_global_search_exact_total_and_pages(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    page: int,
    result_count: int,
    expected_has_more: bool,
):
    mock_tcgdex.get_cards_search.return_value = [
        {"id": f"base1-{i}", "localId": str(i), "name": "Card"} for i in range(53)
    ]

    response = client.get(f"/api/v1/cards?page={page}&page_size=24")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 53
    assert len(data["items"]) == result_count
    assert [c["external_id"] for c in data["items"]] == [
        f"base1-{i}" for i in range((page - 1) * 24, min(page * 24, 53))
    ]
    assert data["has_more"] is expected_has_more
    mock_tcgdex.get_cards_search.assert_awaited_once_with(
        name=None, local_id=None, page=None, language="en"
    )


def test_global_search_cache_shared_across_pages(client, mock_tcgdex):
    mock_tcgdex.get_cards_search.return_value = [
        {"id": f"base1-{i}", "localId": str(i), "name": "Pikachu"} for i in range(5)
    ] + [{"id": "tcgp-1", "localId": "1", "name": "Pocket"}]
    first = client.get("/api/v1/cards?name=Pikachu&page_size=2").json()
    second = client.get("/api/v1/cards?name=Pikachu&page_size=3&page=2").json()
    assert first["total"] == second["total"] == 5
    assert len(first["items"]) == len(second["items"]) == 2
    assert first["has_more"] is True
    assert second["has_more"] is False
    mock_tcgdex.get_cards_search.assert_awaited_once()
    client.get("/api/v1/cards?name=Eevee&page_size=2")
    assert mock_tcgdex.get_cards_search.await_count == 2


def test_list_cards_global_search_filters_digital_cards(
    client: TestClient, mock_tcgdex: AsyncMock
):
    """Verify digital cards (e.g. series tcgp or pocket) are filtered out."""
    mock_results = [
        {
            "id": "base1-58",
            "localId": "58",
            "name": "Pikachu",
            "image": "https://assets.tcgdex.net/en/base/base1/58",
        },
        {
            "id": "tcgp-01",
            "localId": "1",
            "name": "Pikachu Pocket",
            "image": "https://assets.tcgdex.net/en/tcgp/A1/1",
        },
    ]
    mock_tcgdex.get_cards_search.return_value = mock_results

    res = client.get("/api/v1/cards?name=pikachu")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["external_id"] == "base1-58"


def test_list_cards_with_digital_set_returns_empty(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_digital_set_fixture: dict,
):
    """Verify browsing cards for a digital set returns empty response."""
    mock_tcgdex.get_set.return_value = sample_digital_set_fixture

    res = client.get("/api/v1/cards?set_id=A1")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert len(data["items"]) == 0
    assert data["has_more"] is False


def test_list_cards_pagination(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
):
    """Verify in-memory pagination and has_more flag when browsing set cards."""
    mock_tcgdex.get_set.return_value = sample_set_fixture

    # Page 1 (2 items)
    res_p1 = client.get("/api/v1/cards?set_id=base1&page=1&page_size=2")
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert d1["total"] == 5
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert d1["has_more"] is True
    assert len(d1["items"]) == 2
    assert [c["local_id"] for c in d1["items"]] == ["1", "2"]

    # Page 2 (2 items)
    res_p2 = client.get("/api/v1/cards?set_id=base1&page=2&page_size=2")
    assert res_p2.status_code == 200
    d2 = res_p2.json()
    assert d2["total"] == 5
    assert d2["page"] == 2
    assert d2["has_more"] is True
    assert len(d2["items"]) == 2
    assert [c["local_id"] for c in d2["items"]] == ["003", "TG01"]

    # Page 3 (1 item, last page)
    res_p3 = client.get("/api/v1/cards?set_id=base1&page=3&page_size=2")
    assert res_p3.status_code == 200
    d3 = res_p3.json()
    assert d3["total"] == 5
    assert d3["page"] == 3
    assert d3["has_more"] is False
    assert len(d3["items"]) == 1
    assert d3["items"][0]["local_id"] == "5"


def test_get_card_detail_unified_success(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_card_detail_fixture: dict,
):
    """Verify GET /api/v1/cards/{external_id} returns unified metadata with empty DB."""
    # Add set object to card detail fixture
    card_with_set = {
        **sample_card_detail_fixture,
        "set": {
            "id": "base1",
            "name": "Base Set",
        },
    }
    mock_tcgdex.get_card.return_value = card_with_set

    res = client.get("/api/v1/cards/base1-1")
    assert res.status_code == 200
    data = res.json()

    assert data["external_id"] == "base1-1"
    assert data["id"] == "base1-1"
    assert data["name"] == "Alakazam"
    assert data["local_id"] == "1"
    assert data["language"] == "en"
    assert data["status"] == "available"
    assert data["category"] == "Pokemon"
    assert data["illustrator"] == "Ken Sugimori"
    assert data["rarity"] == "Rare Holo"
    assert data["hp"] == 80
    assert data["types"] == ["Psychic"]
    assert data["set"]["external_id"] == "base1"
    assert data["set"]["name"] == "Base Set"
    assert (
        data["small_image_url"] == "https://assets.tcgdex.net/en/base/base1/1/low.webp"
    )
    assert (
        data["large_image_url"] == "https://assets.tcgdex.net/en/base/base1/1/high.webp"
    )
    assert len(data["attacks"]) == 1
    assert data["attacks"][0]["name"] == "Confuse Ray"
    assert data["attacks"][0]["damage"] == 30
    assert len(data["abilities"]) == 1
    assert data["abilities"][0]["name"] == "Damage Swap"
    assert "pricing" not in data

    mock_tcgdex.get_card.assert_awaited_once_with("base1-1", language="en")


def test_get_card_detail_not_found(client: TestClient, mock_tcgdex: AsyncMock):
    """Verify 404 for unknown card ID."""
    mock_tcgdex.get_card.return_value = None

    res = client.get("/api/v1/cards/unknown-card")
    assert res.status_code == 404
    assert res.json()["detail"] == "Card not found"


def test_get_card_detail_excludes_digital(client: TestClient, mock_tcgdex: AsyncMock):
    """Verify 404 for pocket / digital card."""
    mock_tcgdex.get_card.return_value = {
        "id": "A1-1",
        "localId": "1",
        "name": "Bulbasaur",
        "image": "https://assets.tcgdex.net/en/tcgp/A1/1",
        "set": {
            "id": "A1",
            "name": "Genetic Apex",
            "serie": {"id": "tcgp", "name": "Pokémon TCG Pocket"},
        },
    }

    res = client.get("/api/v1/cards/A1-1")
    assert res.status_code == 404
    assert res.json()["detail"] == "Card not found"


def test_cards_api_upstream_503_without_cache(
    client: TestClient,
    mock_tcgdex: AsyncMock,
):
    """Verify HTTP 503 when TCGdex fails and no cached data exists."""
    mock_tcgdex.get_cards_search.side_effect = TcgdexConnectionError("Upstream timeout")
    res_list = client.get("/api/v1/cards?name=pikachu")
    assert res_list.status_code == 503
    assert res_list.json()["detail"] == "Cards catalog temporarily unavailable"

    mock_tcgdex.get_card.side_effect = TcgdexConnectionError("Upstream timeout")
    res_detail = client.get("/api/v1/cards/base1-1")
    assert res_detail.status_code == 503
    assert res_detail.json()["detail"] == "Card details temporarily unavailable"


def test_cards_api_serves_stale_cache_on_upstream_failure(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_card_detail_fixture: dict,
):
    """Verify HTTP 200 serves bounded stale data if upstream fails."""
    # 1. Prime cache with successful initial fetch
    mock_tcgdex.get_card.return_value = sample_card_detail_fixture
    res_prime = client.get("/api/v1/cards/base1-1")
    assert res_prime.status_code == 200
    assert res_prime.json()["status"] == "available"

    # 2. Age cache entries past fresh TTL (7 hours; fresh TTL is 6h, max stale 24h)
    for key, entry in list(catalog_cache._store.items()):
        catalog_cache._store[key] = CacheEntry(
            details=entry.details,
            fetched_at=entry.fetched_at - timedelta(hours=7),
        )

    # 3. Upstream fails
    mock_tcgdex.get_card.side_effect = TcgdexConnectionError("Connection refused")

    # 4. Should serve stale cache with 200 and status="stale"
    res_stale = client.get("/api/v1/cards/base1-1")
    assert res_stale.status_code == 200
    data = res_stale.json()
    assert data["status"] == "stale"
    assert data["external_id"] == "base1-1"
    assert data["name"] == "Alakazam"


def test_get_card_enrichment_legacy_endpoint(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_card_detail_fixture: dict,
):
    """Verify legacy /details endpoint compatibility with string external_id."""
    mock_tcgdex.get_card.return_value = sample_card_detail_fixture

    res = client.get("/api/v1/cards/base1-1/details")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "available"
    assert data["source"] == "tcgdex"
    assert data["details"]["category"] == "Pokemon"
    assert data["details"]["rarity"] == "Rare Holo"
    assert "pricing" not in data["details"]


def test_cards_api_language_validation(client: TestClient):
    """Verify unsupported language codes return HTTP 400."""
    res_list = client.get("/api/v1/cards?language=unsupported_lang")
    assert res_list.status_code == 400
    assert "not supported" in res_list.json()["detail"].lower()

    res_card = client.get("/api/v1/cards/base1-1?language=unsupported_lang")
    assert res_card.status_code == 400
    assert "not supported" in res_card.json()["detail"].lower()


def test_cards_api_input_validation(client: TestClient):
    """Verify pagination boundary constraints."""
    res_page_zero = client.get("/api/v1/cards?page=0")
    assert res_page_zero.status_code == 422

    res_large_size = client.get("/api/v1/cards?page_size=101")
    assert res_large_size.status_code == 422
