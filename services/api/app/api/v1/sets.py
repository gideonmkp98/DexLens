from fastapi import APIRouter, Depends, HTTPException, Query

from app.integrations.tcgdex.mapper import is_digital_set
from app.schemas.set import PaginatedSetsResponse, SetDetailResponse, SetSummaryResponse
from app.services.card_catalog import CardCatalogService, get_card_catalog_service
from app.services.detail_cache import catalog_cache

router = APIRouter(prefix="/sets", tags=["Sets"])

# Reusable service for catalog requests in API process
_catalog_service = get_card_catalog_service()

# Backward-compatibility alias for test dependency overrides and external callers
get_tcgdex_client = get_card_catalog_service


@router.get("", response_model=PaginatedSetsResponse)
async def list_sets(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(24, ge=1, le=100, description="Items per page"),
    language: str = Query("en", description="Language code filter"),
    client: CardCatalogService = Depends(get_card_catalog_service),
) -> PaginatedSetsResponse:
    """Retrieve paginated list of physical sets from TCGdex catalog cache."""
    clean_lang = language.lower().strip()

    async def fetch_sets() -> list[dict]:
        return await client.get_sets(language=clean_lang)

    result = await catalog_cache.get_or_fetch(
        resource="sets",
        source="tcgdex",
        language=clean_lang,
        external_id="all",
        fetcher=fetch_sets,
    )

    if result.status == "unavailable" or result.details is None:
        raise HTTPException(
            status_code=503,
            detail="Sets catalog temporarily unavailable",
        )

    raw_sets = result.details
    if not isinstance(raw_sets, list):
        raise HTTPException(
            status_code=503,
            detail="Sets catalog temporarily unavailable",
        )

    # Filter out digital sets
    physical_sets = [s for s in raw_sets if not is_digital_set(s)]

    # Map each physical set to SetSummaryResponse
    items: list[SetSummaryResponse] = []
    for s in physical_sets:
        card_count_dict = (
            s.get("cardCount") if isinstance(s.get("cardCount"), dict) else {}
        )
        printed_total = card_count_dict.get("official")
        total = card_count_dict.get("total")
        card_count = total or 0
        series_name = (
            s.get("serie", {}).get("name") if isinstance(s.get("serie"), dict) else None
        )
        items.append(
            SetSummaryResponse(
                id=s.get("id"),
                source="tcgdex",
                external_id=s.get("id", ""),
                name=s.get("name", ""),
                language=clean_lang,
                series=series_name,
                logo_url=s.get("logo"),
                symbol_url=s.get("symbol"),
                release_date=s.get("releaseDate"),
                printed_total=printed_total,
                total=total,
                card_count=card_count,
                local_card_count=card_count,
            )
        )

    total_count = len(items)
    start_idx = (page - 1) * page_size
    end_idx = page * page_size
    paginated_items = items[start_idx:end_idx]
    has_more = end_idx < total_count

    return PaginatedSetsResponse(
        items=paginated_items,
        total=total_count,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/{external_id}", response_model=SetDetailResponse)
async def get_set(
    external_id: str,
    language: str = Query("en", description="Language code"),
    client: CardCatalogService = Depends(get_card_catalog_service),
) -> SetDetailResponse:
    """Retrieve detailed set metadata including card count from catalog cache."""
    clean_lang = language.lower().strip()

    async def fetch_set() -> dict | None:
        return await client.get_set(external_id, language=clean_lang)

    result = await catalog_cache.get_or_fetch(
        resource="set",
        source="tcgdex",
        language=clean_lang,
        external_id=external_id,
        fetcher=fetch_set,
    )

    if result.status == "unavailable" or result.details is None:
        if result.error is not None:
            raise HTTPException(
                status_code=503,
                detail="Set details temporarily unavailable",
            )
        raise HTTPException(status_code=404, detail="Set not found")

    set_data = result.details
    if not isinstance(set_data, dict):
        raise HTTPException(status_code=404, detail="Set not found")

    if is_digital_set(set_data):
        raise HTTPException(status_code=404, detail="Set not found")

    card_count_dict = (
        set_data.get("cardCount") if isinstance(set_data.get("cardCount"), dict) else {}
    )
    printed_total = card_count_dict.get("official")
    total = card_count_dict.get("total")

    cards_list = set_data.get("cards")
    if isinstance(cards_list, list) and cards_list:
        card_count = len(cards_list)
    else:
        card_count = total or 0

    series_name = (
        set_data.get("serie", {}).get("name")
        if isinstance(set_data.get("serie"), dict)
        else None
    )

    return SetDetailResponse(
        id=set_data.get("id") or external_id,
        source="tcgdex",
        external_id=set_data.get("id") or external_id,
        name=set_data.get("name", ""),
        language=clean_lang,
        series=series_name,
        logo_url=set_data.get("logo"),
        symbol_url=set_data.get("symbol"),
        release_date=set_data.get("releaseDate"),
        printed_total=printed_total,
        total=total,
        card_count=card_count,
        local_card_count=card_count,
    )
