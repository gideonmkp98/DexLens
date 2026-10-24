from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.sets import get_tcgdex_client
from app.main import app
from app.services.detail_cache import CacheEntry, catalog_cache
from app.services.tcgdex import TcgdexClient, TcgdexConnectionError


@pytest.fixture(autouse=True)
def clear_catalog_cache():
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


def test_list_sets_empty_db_success(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
):
    """Verify GET /api/v1/sets returns physical sets when MariaDB has no records."""
    mock_tcgdex.get_sets.return_value = [sample_set_fixture]

    res = client.get("/api/v1/sets")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["page_size"] == 24
    assert data["has_more"] is False
    assert len(data["items"]) == 1

    item = data["items"][0]
    assert item["external_id"] == "base1"
    assert item["name"] == "Base Set"
    assert item["series"] == "Base"
    assert item["card_count"] == 102
    assert item["local_card_count"] == 102
    assert item["printed_total"] == 102
    assert item["total"] == 102
    assert item["release_date"] == "1999-01-09"
    mock_tcgdex.get_sets.assert_awaited_once_with(language="en")


def test_list_sets_filters_digital_sets(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
    sample_digital_set_fixture: dict,
):
    """Verify digital sets (e.g. series 'tcgp' or containing Pocket) are excluded."""
    mock_tcgdex.get_sets.return_value = [
        sample_set_fixture,
        sample_digital_set_fixture,
    ]

    res = client.get("/api/v1/sets")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["external_id"] == "base1"


def test_list_sets_pagination(client: TestClient, mock_tcgdex: AsyncMock):
    """Verify page and page_size slicing and has_more flag."""
    sets_data = [
        {
            "id": f"set-{i}",
            "name": f"Set {i}",
            "serie": {"id": "main", "name": "Main Series"},
            "cardCount": {"official": 50, "total": 50},
        }
        for i in range(1, 6)
    ]
    mock_tcgdex.get_sets.return_value = sets_data

    # Page 1 (2 items)
    res_p1 = client.get("/api/v1/sets?page=1&page_size=2")
    assert res_p1.status_code == 200
    d1 = res_p1.json()
    assert d1["total"] == 5
    assert d1["page"] == 1
    assert d1["page_size"] == 2
    assert d1["has_more"] is True
    assert [s["external_id"] for s in d1["items"]] == ["set-1", "set-2"]

    # Page 2 (2 items)
    res_p2 = client.get("/api/v1/sets?page=2&page_size=2")
    assert res_p2.status_code == 200
    d2 = res_p2.json()
    assert d2["total"] == 5
    assert d2["page"] == 2
    assert d2["has_more"] is True
    assert [s["external_id"] for s in d2["items"]] == ["set-3", "set-4"]

    # Page 3 (1 item, last page)
    res_p3 = client.get("/api/v1/sets?page=3&page_size=2")
    assert res_p3.status_code == 200
    d3 = res_p3.json()
    assert d3["total"] == 5
    assert d3["page"] == 3
    assert d3["has_more"] is False
    assert [s["external_id"] for s in d3["items"]] == ["set-5"]


def test_get_set_detail_success(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
):
    """Verify GET /api/v1/sets/base1 returns metadata and card count with empty DB."""
    mock_tcgdex.get_set.return_value = sample_set_fixture

    res = client.get("/api/v1/sets/base1")
    assert res.status_code == 200
    data = res.json()
    assert data["external_id"] == "base1"
    assert data["id"] == "base1"
    assert data["name"] == "Base Set"
    assert data["series"] == "Base"
    assert data["card_count"] == 5  # 5 cards in sample_set_fixture["cards"]
    assert data["local_card_count"] == 5
    assert data["printed_total"] == 102
    assert data["total"] == 102
    assert data["release_date"] == "1999-01-09"
    mock_tcgdex.get_set.assert_awaited_once_with("base1", language="en")


def test_get_set_detail_not_found(client: TestClient, mock_tcgdex: AsyncMock):
    """Verify 404 for unknown set ID."""
    mock_tcgdex.get_set.return_value = None

    res = client.get("/api/v1/sets/unknown-set")
    assert res.status_code == 404
    assert res.json()["detail"] == "Set not found"


def test_get_set_detail_excludes_digital(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_digital_set_fixture: dict,
):
    """Verify 404 for digital set ID."""
    mock_tcgdex.get_set.return_value = sample_digital_set_fixture

    res = client.get("/api/v1/sets/A1")
    assert res.status_code == 404
    assert res.json()["detail"] == "Set not found"


def test_sets_api_upstream_503_without_cache(
    client: TestClient,
    mock_tcgdex: AsyncMock,
):
    """Verify HTTP 503 when TCGdex fails and no cached data exists."""
    mock_tcgdex.get_sets.side_effect = TcgdexConnectionError("Provider timeout")
    res_list = client.get("/api/v1/sets")
    assert res_list.status_code == 503
    assert res_list.json()["detail"] == "Sets catalog temporarily unavailable"

    mock_tcgdex.get_set.side_effect = TcgdexConnectionError("Provider timeout")
    res_detail = client.get("/api/v1/sets/base1")
    assert res_detail.status_code == 503
    assert res_detail.json()["detail"] == "Set details temporarily unavailable"


def test_sets_api_serves_stale_cache_on_upstream_failure(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
):
    """Verify HTTP 200 serves bounded stale data if upstream fails."""
    # 1. Prime cache with successful initial fetch
    mock_tcgdex.get_sets.return_value = [sample_set_fixture]
    mock_tcgdex.get_set.return_value = sample_set_fixture

    res_prime_list = client.get("/api/v1/sets")
    assert res_prime_list.status_code == 200
    res_prime_detail = client.get("/api/v1/sets/base1")
    assert res_prime_detail.status_code == 200
    # 2. Age cache entries past fresh TTL (e.g. 7 hours later;
    # fresh TTL is 6h, max stale 24h)
    for key, entry in list(catalog_cache._store.items()):
        catalog_cache._store[key] = CacheEntry(
            details=entry.details,
            fetched_at=entry.fetched_at - timedelta(hours=7),
        )

    # 3. Upstream fails
    mock_tcgdex.get_sets.side_effect = TcgdexConnectionError("Connection refused")
    mock_tcgdex.get_set.side_effect = TcgdexConnectionError("Connection refused")

    # 4. Should serve stale cache with 200
    res_stale_list = client.get("/api/v1/sets")
    assert res_stale_list.status_code == 200
    data_list = res_stale_list.json()
    assert data_list["total"] == 1
    assert data_list["items"][0]["external_id"] == "base1"

    res_stale_detail = client.get("/api/v1/sets/base1")
    assert res_stale_detail.status_code == 200
    data_detail = res_stale_detail.json()
    assert data_detail["external_id"] == "base1"
    assert data_detail["name"] == "Base Set"


def test_sets_api_supports_language_query(
    client: TestClient,
    mock_tcgdex: AsyncMock,
    sample_set_fixture: dict,
):
    """Verify language query parameter is forwarded to TCGdex client."""
    mock_tcgdex.get_sets.return_value = [sample_set_fixture]
    mock_tcgdex.get_set.return_value = sample_set_fixture

    res_list = client.get("/api/v1/sets?language=fr")
    assert res_list.status_code == 200
    assert res_list.json()["items"][0]["language"] == "fr"
    mock_tcgdex.get_sets.assert_awaited_once_with(language="fr")

    res_detail = client.get("/api/v1/sets/base1?language=fr")
    assert res_detail.status_code == 200
    assert res_detail.json()["language"] == "fr"
    mock_tcgdex.get_set.assert_awaited_once_with("base1", language="fr")


def test_sets_api_input_validation(client: TestClient):
    """Verify input validation for pagination bounds."""
    res_page_zero = client.get("/api/v1/sets?page=0")
    assert res_page_zero.status_code == 422

    res_page_size_large = client.get("/api/v1/sets?page_size=101")
    assert res_page_size_large.status_code == 422
