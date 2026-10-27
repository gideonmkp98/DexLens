from unittest.mock import AsyncMock

import httpx
import pytest

from app.services.tcgdex import (
    TcgdexClient,
    TcgdexConnectionError,
    TcgdexError,
    TcgdexInvalidLanguageError,
)


@pytest.fixture
def mock_httpx_client():
    client = AsyncMock(spec=httpx.AsyncClient)
    return client


@pytest.mark.asyncio
async def test_get_cards_search_query_construction(mock_httpx_client):
    mock_response = httpx.Response(
        status_code=200,
        json=[
            {
                "id": "base1-4",
                "localId": "4",
                "name": "Charizard",
                "image": "https://assets.tcgdex.net/en/base/base1/4",
            }
        ],
        request=httpx.Request("GET", "https://api.tcgdex.net/v2/en/cards"),
    )
    mock_httpx_client.get.return_value = mock_response

    client = TcgdexClient(client=mock_httpx_client)
    cards = await client.get_cards_search(
        name="Charizard",
        local_id="4",
        page=2,
        page_size=12,
        language="en",
    )

    assert len(cards) == 1
    assert cards[0]["id"] == "base1-4"
    assert cards[0]["name"] == "Charizard"

    mock_httpx_client.get.assert_called_once()
    called_url, called_kwargs = mock_httpx_client.get.call_args
    assert called_url[0].endswith("/en/cards")
    assert called_kwargs["params"] == {
        "pagination:page": 2,
        "pagination:itemsPerPage": 12,
        "name": "Charizard",
        "localId": "4",
    }


@pytest.mark.asyncio
async def test_get_cards_search_default_params(mock_httpx_client):
    mock_response = httpx.Response(
        status_code=200,
        json=[],
        request=httpx.Request("GET", "https://api.tcgdex.net/v2/en/cards"),
    )
    mock_httpx_client.get.return_value = mock_response

    client = TcgdexClient(client=mock_httpx_client)
    cards = await client.get_cards_search()

    assert cards == []
    mock_httpx_client.get.assert_called_once()
    called_url, called_kwargs = mock_httpx_client.get.call_args
    assert called_url[0].endswith("/en/cards")
    assert called_kwargs["params"] == {
        "pagination:page": 1,
        "pagination:itemsPerPage": 24,
    }


@pytest.mark.asyncio
async def test_get_cards_search_404_returns_empty_list(mock_httpx_client):
    mock_response = httpx.Response(
        status_code=404,
        request=httpx.Request("GET", "https://api.tcgdex.net/v2/en/cards"),
    )
    mock_httpx_client.get.return_value = mock_response

    client = TcgdexClient(client=mock_httpx_client)
    cards = await client.get_cards_search(name="NonExistentCard")

    assert cards == []


@pytest.mark.asyncio
async def test_get_cards_search_invalid_response_format_raises(
    mock_httpx_client,
):
    mock_response = httpx.Response(
        status_code=200,
        json={"error": "unexpected format"},
        request=httpx.Request("GET", "https://api.tcgdex.net/v2/en/cards"),
    )
    mock_httpx_client.get.return_value = mock_response

    client = TcgdexClient(client=mock_httpx_client)
    with pytest.raises(TcgdexError):
        await client.get_cards_search(name="Whatever")


@pytest.mark.asyncio
async def test_complete_search_omits_provider_pagination(mock_httpx_client):
    mock_httpx_client.get.return_value = httpx.Response(200, json=[])
    client = TcgdexClient(client=mock_httpx_client)
    await client.get_cards_search(name="Pikachu", local_id="001", page=None)
    assert mock_httpx_client.get.call_args.kwargs["params"] == {
        "name": "Pikachu",
        "localId": "001",
    }


@pytest.mark.asyncio
async def test_get_cards_search_unsupported_language(mock_httpx_client):
    client = TcgdexClient(client=mock_httpx_client)
    with pytest.raises(TcgdexInvalidLanguageError):
        await client.get_cards_search(language="klingon")


@pytest.mark.asyncio
async def test_get_cards_search_handles_network_failure(mock_httpx_client):
    mock_httpx_client.get.side_effect = httpx.ConnectError("Connection refused")

    client = TcgdexClient(client=mock_httpx_client, max_retries=1)
    with pytest.raises(TcgdexConnectionError):
        await client.get_cards_search(name="Pikachu")


def test_set_schemas_optional_id_and_card_count():
    from app.schemas.set import (
        PaginatedSetsResponse,
        SetDetailResponse,
        SetSummaryResponse,
    )

    # Test SetSummaryResponse without DB id
    set_summary = SetSummaryResponse(
        external_id="base1",
        name="Base Set",
        card_count=102,
        release_date="1999-01-09",
    )
    assert set_summary.id is None
    assert set_summary.external_id == "base1"
    assert set_summary.card_count == 102
    assert set_summary.local_card_count == 0
    assert set_summary.source == "tcgdex"
    assert set_summary.language == "en"

    # Test SetDetailResponse with string id
    set_detail = SetDetailResponse(
        id="base1",
        external_id="base1",
        name="Base Set",
        card_count=102,
    )
    assert set_detail.id == "base1"
    assert set_detail.card_count == 102

    # Test PaginatedSetsResponse has_more default and explicit
    paginated = PaginatedSetsResponse(
        items=[set_summary],
        total=1,
        page=1,
        page_size=24,
    )
    assert paginated.has_more is False

    paginated_more = PaginatedSetsResponse(
        items=[set_summary],
        total=50,
        page=1,
        page_size=24,
        has_more=True,
    )
    assert paginated_more.has_more is True


def test_card_schemas_unified_attributes():
    from app.schemas.card import (
        CardDetailResponse,
        CardListItem,
        CardSetBrief,
        PaginatedCardsResponse,
    )

    # Test CardSetBrief
    brief1 = CardSetBrief(id="base1", name="Base Set")
    assert brief1.external_id == "base1"
    brief2 = CardSetBrief(external_id="base2", name="Jungle")
    assert brief2.id == "base2"

    # Test CardListItem with string set_id
    card_item = CardListItem(
        external_id="base1-4",
        set_id="base1",
        local_id="4",
        name="Charizard",
        small_image_url="https://assets.tcgdex.net/en/base/base1/4/low.webp",
    )
    assert card_item.id is None
    assert card_item.set_id == "base1"
    assert card_item.source == "tcgdex"
    assert card_item.language == "en"

    # Test CardDetailResponse with full unified attributes
    card_detail = CardDetailResponse(
        external_id="base1-4",
        set_id="base1",
        local_id="4",
        name="Charizard",
        set=brief1,
        status="available",
        category="Pokemon",
        illustrator="Mitsuhiro Arita",
        rarity="Rare Holo",
        hp=120,
        types=["Fire"],
        regulationMark="D",
        variants={"normal": False, "holo": True},
        attacks=[{"name": "Fire Spin", "damage": "100"}],
        abilities=[{"name": "Energy Burn", "type": "Pokemon Power"}],
    )
    assert card_detail.id is None
    assert card_detail.external_id == "base1-4"
    assert card_detail.set.name == "Base Set"
    assert card_detail.hp == 120
    assert card_detail.regulation_mark == "D"
    assert card_detail.attacks[0]["name"] == "Fire Spin"

    # Test PaginatedCardsResponse
    paginated_cards = PaginatedCardsResponse(
        items=[card_item],
        total=100,
        page=1,
        page_size=24,
        has_more=True,
    )
    assert paginated_cards.has_more is True
    assert len(paginated_cards.items) == 1
