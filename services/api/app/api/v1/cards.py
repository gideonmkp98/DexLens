from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.config import settings
from app.schemas.card import (
    CardDetailResponse,
    CardEnrichmentResponse,
    CardListItem,
    CardSetBrief,
    PaginatedCardsResponse,
)
from app.services.detail_cache import catalog_cache, map_card_details
from app.services.tcgdex import TcgdexClient, is_digital_card, is_digital_set

router = APIRouter(prefix="/cards", tags=["Cards"])

# Reusable client for catalog requests in API process
_tcgdex_client = TcgdexClient()


def get_tcgdex_client() -> TcgdexClient:
    return _tcgdex_client


def _derive_image_urls(base_url: str | None) -> tuple[str | None, str | None]:
    if not base_url:
        return None, None
    clean = base_url.rstrip("/")
    if clean.endswith("/low.webp") or clean.endswith("/high.webp"):
        clean = clean.rsplit("/", 1)[0]
    return f"{clean}/low.webp", f"{clean}/high.webp"


def _validate_language(language: str) -> str:
    clean_lang = language.lower().strip()
    if clean_lang not in settings.SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Language '{language}' is not supported. "
                f"Supported: {settings.SUPPORTED_LANGUAGES}"
            ),
        )
    return clean_lang


@router.get("", response_model=PaginatedCardsResponse)
async def list_cards(
    name: str | None = Query(
        None, description="Case-insensitive partial match against card name"
    ),
    number: str | None = Query(
        None, description="Exact match against card local number"
    ),
    set_id: str | None = Query(None, description="Provider set ID (e.g. base1)"),
    language: str = Query("en", description="Card language code"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(24, ge=1, le=100, description="Items per page"),
    client: TcgdexClient = Depends(get_tcgdex_client),
) -> PaginatedCardsResponse:
    """Retrieve paginated cards from catalog cache. Decoupled from MariaDB."""
    clean_lang = _validate_language(language)

    # Case A: Filter cards within a specific set
    if set_id is not None:

        async def fetch_set() -> dict | None:
            return await client.get_set(set_id, language=clean_lang)

        result = await catalog_cache.get_or_fetch(
            resource="set",
            source="tcgdex",
            language=clean_lang,
            external_id=set_id,
            fetcher=fetch_set,
        )

        if result.status == "unavailable" or result.details is None:
            if result.error is not None:
                raise HTTPException(
                    status_code=503,
                    detail="Cards catalog temporarily unavailable",
                )
            return PaginatedCardsResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                has_more=False,
            )

        set_data = result.details
        if not isinstance(set_data, dict) or is_digital_set(set_data):
            return PaginatedCardsResponse(
                items=[],
                total=0,
                page=page,
                page_size=page_size,
                has_more=False,
            )

        raw_cards = set_data.get("cards", [])
        if not isinstance(raw_cards, list):
            raw_cards = []

        clean_name = name.lower().strip() if name else None
        clean_number = number.strip() if number else None
        filtered = []

        for c in raw_cards:
            if not isinstance(c, dict):
                continue
            if is_digital_card(c):
                continue
            if clean_name and clean_name not in str(c.get("name", "")).lower():
                continue
            if clean_number and str(c.get("localId", "")).strip() != clean_number:
                continue
            filtered.append(c)

        total = len(filtered)
        start_idx = (page - 1) * page_size
        end_idx = page * page_size
        slice_cards = filtered[start_idx:end_idx]
        has_more = end_idx < total

        set_name = set_data.get("name")
        items: list[CardListItem] = []
        for c in slice_cards:
            image_base = c.get("image")
            small_url, large_url = _derive_image_urls(image_base)
            card_id = c.get("id") or f"{set_id}-{c.get('localId')}"
            items.append(
                CardListItem(
                    id=str(card_id),
                    source="tcgdex",
                    external_id=str(card_id),
                    set_id=str(set_id),
                    local_id=str(c.get("localId", "")),
                    name=c.get("name", ""),
                    language=clean_lang,
                    image_base_url=image_base,
                    small_image_url=small_url,
                    large_image_url=large_url,
                    set_name=set_name,
                )
            )

        return PaginatedCardsResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            has_more=has_more,
        )

    # Case B: Global card search across all sets
    clean_name_param = name.strip() if name else None
    clean_number_param = number.strip() if number else None
    query_str = (
        f"name={clean_name_param or ''}&"
        f"localId={clean_number_param or ''}&"
        f"page={page}&size={page_size}"
    )

    async def fetch_search() -> list[dict]:
        return await client.get_cards_search(
            name=clean_name_param,
            local_id=clean_number_param,
            page=page,
            page_size=page_size,
            language=clean_lang,
        )

    result = await catalog_cache.get_or_fetch(
        resource="search",
        source="tcgdex",
        language=clean_lang,
        external_id=query_str,
        fetcher=fetch_search,
    )

    if result.status == "unavailable" or result.details is None:
        if result.error is not None:
            raise HTTPException(
                status_code=503,
                detail="Cards catalog temporarily unavailable",
            )
        raw_cards = []
    else:
        raw_cards = result.details
        if not isinstance(raw_cards, list):
            raw_cards = []

    physical_cards = [
        c for c in raw_cards if isinstance(c, dict) and not is_digital_card(c)
    ]

    has_more = len(raw_cards) == page_size
    total = (
        len(physical_cards)
        if (not has_more and page == 1)
        else (
            (page * page_size + 1)
            if has_more
            else ((page - 1) * page_size + len(physical_cards))
        )
    )

    items = []
    for c in physical_cards:
        image_base = c.get("image")
        small_url, large_url = _derive_image_urls(image_base)
        card_id = c.get("id", "")
        set_info = c.get("set") if isinstance(c.get("set"), dict) else {}
        card_set_id = set_info.get("id")
        if not card_set_id and "-" in str(card_id):
            card_set_id = str(card_id).rsplit("-", 1)[0]
        set_name = set_info.get("name")

        items.append(
            CardListItem(
                id=str(card_id),
                source="tcgdex",
                external_id=str(card_id),
                set_id=str(card_set_id or ""),
                local_id=str(c.get("localId", "")),
                name=c.get("name", ""),
                language=clean_lang,
                image_base_url=image_base,
                small_image_url=small_url,
                large_image_url=large_url,
                set_name=set_name,
            )
        )

    return PaginatedCardsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/{external_id}", response_model=CardDetailResponse)
async def get_card(
    external_id: str,
    language: str = Query("en", description="Card language code"),
    client: TcgdexClient = Depends(get_tcgdex_client),
) -> CardDetailResponse:
    """Retrieve detailed card metadata and attributes from catalog cache."""
    clean_lang = _validate_language(language)

    async def fetch_card() -> dict | None:
        return await client.get_card(external_id, language=clean_lang)

    result = await catalog_cache.get_or_fetch(
        resource="card",
        source="tcgdex",
        language=clean_lang,
        external_id=external_id,
        fetcher=fetch_card,
    )

    if result.status == "unavailable" or result.details is None:
        if result.error is not None:
            raise HTTPException(
                status_code=503,
                detail="Card details temporarily unavailable",
            )
        raise HTTPException(status_code=404, detail="Card not found")

    card_data = result.details
    if not isinstance(card_data, dict) or is_digital_card(card_data):
        raise HTTPException(status_code=404, detail="Card not found")

    details = map_card_details(card_data)
    image_base = card_data.get("image")
    small_url, large_url = _derive_image_urls(image_base)

    set_dict = card_data.get("set")
    set_brief = None
    card_set_id = None
    if isinstance(set_dict, dict):
        card_set_id = str(set_dict.get("id") or "")
        set_brief = CardSetBrief(
            id=set_dict.get("id"),
            external_id=str(set_dict.get("id") or ""),
            name=set_dict.get("name", ""),
        )
    elif "-" in external_id:
        card_set_id = external_id.rsplit("-", 1)[0]

    return CardDetailResponse(
        id=card_data.get("id") or external_id,
        source="tcgdex",
        external_id=card_data.get("id") or external_id,
        set_id=card_set_id,
        local_id=str(card_data.get("localId", "")),
        name=card_data.get("name", ""),
        language=clean_lang,
        image_base_url=image_base,
        small_image_url=small_url,
        large_image_url=large_url,
        set=set_brief,
        status=result.status,
        category=details.get("category"),
        illustrator=details.get("illustrator"),
        rarity=details.get("rarity"),
        hp=details.get("hp"),
        types=details.get("types"),
        regulation_mark=details.get("regulationMark"),
        variants=details.get("variants"),
        attacks=details.get("attacks"),
        abilities=details.get("abilities"),
    )


@router.get("/{external_id}/details", response_model=CardEnrichmentResponse)
async def get_card_details(
    external_id: str,
    language: str = Query("en", description="Card language code"),
    client: TcgdexClient = Depends(get_tcgdex_client),
) -> CardEnrichmentResponse:
    """Fetch on-demand card enrichment details via catalog cache."""
    clean_lang = _validate_language(language)

    async def fetch_card() -> dict | None:
        return await client.get_card(external_id, language=clean_lang)

    result = await catalog_cache.get_or_fetch(
        resource="card",
        source="tcgdex",
        language=clean_lang,
        external_id=external_id,
        fetcher=fetch_card,
    )

    if result.status == "unavailable" or result.details is None:
        if result.error is not None:
            raise HTTPException(
                status_code=503,
                detail="Card details temporarily unavailable",
            )
        raise HTTPException(status_code=404, detail="Card not found")

    card_data = result.details
    if not isinstance(card_data, dict) or is_digital_card(card_data):
        raise HTTPException(status_code=404, detail="Card not found")

    details = map_card_details(card_data)

    return CardEnrichmentResponse(
        status=result.status,
        source="tcgdex",
        fetched_at=result.fetched_at,
        details=details,
    )
