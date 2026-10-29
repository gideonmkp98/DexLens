import json
import urllib.error
from unittest.mock import AsyncMock, MagicMock

import pytest
from tcgdexsdk import Card, CardResume, Set, SetResume
from tcgdexsdk.models.SerieResume import SerieResume
from tcgdexsdk.models.subs import (
    CardAbility,
    CardAttack,
    CardVariants,
    SetCardCountResume,
)

from app.integrations.tcgdex import (
    TcgdexConnectionError,
    TcgdexError,
    TcgdexInvalidLanguageError,
    TCGdexProvider,
    TcgdexRateLimitError,
    derive_image_urls,
)
from app.services.card_catalog import CardCatalogService


@pytest.fixture
def mock_sdk():
    sdk = MagicMock()
    sdk.card = MagicMock()
    sdk.card.get = AsyncMock()
    sdk.card.list = AsyncMock()
    sdk.set = MagicMock()
    sdk.set.get = AsyncMock()
    sdk.set.list = AsyncMock()
    return sdk


@pytest.fixture
def sample_sdk_card():
    card = Card(
        id="base1-4",
        localId="4",
        name="Charizard",
        image="https://assets.tcgdex.net/en/base/base1/4",
        category="Pokemon",
        illustrator="Mitsuhiro Arita",
        rarity="Rare Holo",
        hp=120,
        types=["Fire"],
        regulationMark="D",
        variants=CardVariants(
            normal=False, reverse=False, holo=True, firstEdition=True, wPromo=False
        ),
        set=SetResume(
            id="base1",
            name="Base Set",
            logo=None,
            symbol=None,
            cardCount=SetCardCountResume(total=102, official=102),
        ),
        attacks=[
            CardAttack(
                name="Fire Spin",
                cost=["Fire", "Fire", "Fire", "Fire"],
                damage=100,
                effect=(
                    "Discard 2 Energy cards attached to Charizard in order "
                    "to use this attack."
                ),
            )
        ],
        abilities=[
            CardAbility(
                type="Pokemon Power",
                name="Energy Burn",
                effect=(
                    "As often as you like during your turn, you may turn all "
                    "Energy into Fire."
                ),
            )
        ],
        dexId=[6],
        evolveFrom="Charmeleon",
        description="Spits fire that is hot enough to melt boulders.",
        level="76",
        stage="Stage 2",
        suffix=None,
        item=None,
        weaknesses=None,
        resistances=None,
        retreat=3,
        effect=None,
        trainerType=None,
        energyType=None,
        legal=None,
        boosters=None,
    )
    card.sdk = MagicMock()
    return card


@pytest.fixture
def sample_sdk_set():
    s = Set(
        id="base1",
        name="Base Set",
        logo="https://assets.tcgdex.net/en/base/base1/logo",
        symbol="https://assets.tcgdex.net/univ/base/base1/symbol",
        releaseDate="1999-01-09",
        cardCount=SetCardCountResume(total=102, official=102),
        serie=SerieResume(id="base", name="Base", logo=None),
        cards=[
            CardResume(
                id="base1-1",
                localId="1",
                name="Alakazam",
                image="https://assets.tcgdex.net/en/base/base1/1",
            ),
            CardResume(
                id="base1-4",
                localId="4",
                name="Charizard",
                image="https://assets.tcgdex.net/en/base/base1/4",
            ),
        ],
        tcgOnline=None,
        legal=None,
        boosters=None,
        abbreviations=None,
    )
    s.sdk = MagicMock()
    return s


@pytest.mark.asyncio
async def test_get_cards_search_query_construction(mock_sdk):
    mock_sdk.card.list.return_value = [
        CardResume(
            id="base1-4",
            localId="4",
            name="Charizard",
            image="https://assets.tcgdex.net/en/base/base1/4",
        )
    ]

    provider = TCGdexProvider(sdk=mock_sdk)
    cards = await provider.search_cards(
        name="Charizard",
        local_id="4",
        page=2,
        page_size=12,
        language="en",
    )

    assert len(cards) == 1
    assert cards[0]["id"] == "base1-4"
    assert cards[0]["name"] == "Charizard"

    mock_sdk.card.list.assert_called_once()
    called_query = mock_sdk.card.list.call_args[0][0]
    built_query = called_query.build()
    assert "name=Charizard" in built_query
    assert "localId=4" in built_query
    assert "pagination%3Apage=2" in built_query
    assert "pagination%3AitemsPerPage=12" in built_query


@pytest.mark.asyncio
async def test_get_cards_search_default_params(mock_sdk):
    mock_sdk.card.list.return_value = []

    provider = TCGdexProvider(sdk=mock_sdk)
    cards = await provider.search_cards()

    assert cards == []
    mock_sdk.card.list.assert_called_once()
    called_query = mock_sdk.card.list.call_args[0][0]
    built_query = called_query.build()
    assert "pagination%3Apage=1" in built_query
    assert "pagination%3AitemsPerPage=24" in built_query


@pytest.mark.asyncio
async def test_get_cards_search_404_returns_empty_list(mock_sdk):
    err404 = urllib.error.HTTPError(
        url="https://api.tcgdex.net/v2/en/cards",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )
    mock_sdk.card.list.side_effect = err404

    provider = TCGdexProvider(sdk=mock_sdk)
    cards = await provider.search_cards(name="NonExistentCard")

    assert cards == []


@pytest.mark.asyncio
async def test_get_card_maps_correctly(mock_sdk, sample_sdk_card):
    mock_sdk.card.get.return_value = sample_sdk_card

    provider = TCGdexProvider(sdk=mock_sdk)
    card_dict = await provider.get_card("base1-4")

    assert card_dict is not None
    assert card_dict["id"] == "base1-4"
    assert card_dict["name"] == "Charizard"
    assert card_dict["localId"] == "4"
    assert card_dict["hp"] == 120
    assert card_dict["category"] == "Pokemon"
    assert card_dict["illustrator"] == "Mitsuhiro Arita"
    assert card_dict["rarity"] == "Rare Holo"
    assert "sdk" not in card_dict
    assert "sdk" not in card_dict["set"]
    assert card_dict["attacks"][0]["name"] == "Fire Spin"
    assert card_dict["abilities"][0]["name"] == "Energy Burn"


@pytest.mark.asyncio
async def test_get_set_maps_correctly(mock_sdk, sample_sdk_set):
    mock_sdk.set.get.return_value = sample_sdk_set

    provider = TCGdexProvider(sdk=mock_sdk)
    set_dict = await provider.get_set("base1")

    assert set_dict is not None
    assert set_dict["id"] == "base1"
    assert set_dict["name"] == "Base Set"
    assert set_dict["releaseDate"] == "1999-01-09"
    assert set_dict["cardCount"]["total"] == 102
    assert len(set_dict["cards"]) == 2
    assert set_dict["cards"][0]["name"] == "Alakazam"
    assert "sdk" not in set_dict


@pytest.mark.asyncio
async def test_get_sets_maps_correctly(mock_sdk):
    mock_sdk.set.list.return_value = [
        SetResume(
            id="base1",
            name="Base Set",
            logo="https://assets.tcgdex.net/en/base/base1/logo",
            symbol=None,
            cardCount=SetCardCountResume(total=102, official=102),
        )
    ]

    provider = TCGdexProvider(sdk=mock_sdk)
    sets = await provider.get_sets()

    assert len(sets) == 1
    assert sets[0]["id"] == "base1"
    assert sets[0]["name"] == "Base Set"
    assert sets[0]["cardCount"]["total"] == 102
    assert "sdk" not in sets[0]


def test_image_url_helpers(sample_sdk_card):
    provider = TCGdexProvider()
    high = provider.get_card_image_url(sample_sdk_card, "high", "webp")
    low = provider.get_card_image_url(sample_sdk_card, "low", "webp")

    assert high == "https://assets.tcgdex.net/en/base/base1/4/high.webp"
    assert low == "https://assets.tcgdex.net/en/base/base1/4/low.webp"

    # Testing derive_image_urls helper directly
    low_derived, high_derived = derive_image_urls("https://assets.tcgdex.net/en/base/base1/4")
    assert low_derived == "https://assets.tcgdex.net/en/base/base1/4/low.webp"
    assert high_derived == "https://assets.tcgdex.net/en/base/base1/4/high.webp"


@pytest.mark.asyncio
async def test_not_found_errors_translated_to_none(mock_sdk):
    err404 = urllib.error.HTTPError(
        url="https://api.tcgdex.net/v2/en/cards/bad",
        code=404,
        msg="Not Found",
        hdrs=None,
        fp=None,
    )
    mock_sdk.card.get.side_effect = err404
    mock_sdk.set.get.side_effect = err404

    provider = TCGdexProvider(sdk=mock_sdk)
    assert await provider.get_card("bad") is None
    assert await provider.get_set("bad") is None


@pytest.mark.asyncio
async def test_provider_errors_do_not_leak_raw_sdk_exceptions(mock_sdk):
    # HTTP 500 error translated to TcgdexConnectionError
    err500 = urllib.error.HTTPError(
        url="https://api.tcgdex.net/v2/en/cards",
        code=500,
        msg="Server Error",
        hdrs=None,
        fp=None,
    )
    mock_sdk.card.get.side_effect = err500
    provider = TCGdexProvider(sdk=mock_sdk, max_retries=1, backoff=0.01)

    with pytest.raises(TcgdexConnectionError):
        await provider.get_card("base1-4")

    # HTTP 429 error translated to TcgdexRateLimitError
    err429 = urllib.error.HTTPError(
        url="https://api.tcgdex.net/v2/en/cards",
        code=429,
        msg="Too Many Requests",
        hdrs=None,
        fp=None,
    )
    mock_sdk.card.get.side_effect = err429
    with pytest.raises(TcgdexRateLimitError):
        await provider.get_card("base1-4")

    # Network error translated to TcgdexConnectionError
    mock_sdk.card.get.side_effect = urllib.error.URLError("Connection refused")
    with pytest.raises(TcgdexConnectionError):
        await provider.get_card("base1-4")

    # Malformed response translated to TcgdexError
    mock_sdk.card.get.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)
    with pytest.raises(TcgdexError):
        await provider.get_card("base1-4")


@pytest.mark.asyncio
async def test_unsupported_language_raises():
    provider = TCGdexProvider()
    with pytest.raises(TcgdexInvalidLanguageError):
        await provider.get_card("base1-4", language="klingon")


@pytest.mark.asyncio
async def test_card_catalog_service_layer(mock_sdk, sample_sdk_card, sample_sdk_set):
    mock_sdk.card.get.return_value = sample_sdk_card
    mock_sdk.set.get.return_value = sample_sdk_set
    provider = TCGdexProvider(sdk=mock_sdk)
    catalog = CardCatalogService(provider=provider)

    card = await catalog.get_card("base1-4")
    assert card["id"] == "base1-4"
    assert card["name"] == "Charizard"

    set_data = await catalog.get_set("base1")
    assert set_data["id"] == "base1"


def test_set_schemas_optional_id_and_card_count():
    from app.schemas.set import (
        PaginatedSetsResponse,
        SetDetailResponse,
        SetSummaryResponse,
    )

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

    set_detail = SetDetailResponse(
        id="base1",
        external_id="base1",
        name="Base Set",
        card_count=102,
    )
    assert set_detail.id == "base1"
    assert set_detail.card_count == 102

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

    brief1 = CardSetBrief(id="base1", name="Base Set")
    assert brief1.external_id == "base1"
    brief2 = CardSetBrief(external_id="base2", name="Jungle")
    assert brief2.id == "base2"

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

    paginated_cards = PaginatedCardsResponse(
        items=[card_item],
        total=100,
        page=1,
        page_size=24,
        has_more=True,
    )
    assert paginated_cards.has_more is True
    assert len(paginated_cards.items) == 1
