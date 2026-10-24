from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.models.card import Card
from app.schemas.card import (
    CardDetailResponse,
    CardEnrichmentResponse,
    CardListItem,
    CardSetBrief,
    PaginatedCardsResponse,
)
from app.services.detail_cache import detail_cache, map_card_details
from app.services.tcgdex import TcgdexClient

router = APIRouter(prefix="/cards", tags=["Cards"])

# Reusable client for on-demand details in API process
_tcgdex_client = TcgdexClient()


def get_tcgdex_client() -> TcgdexClient:
    return _tcgdex_client


def _derive_image_urls(base_url: str | None) -> tuple[str | None, str | None]:
    if not base_url:
        return None, None
    clean = base_url.rstrip("/")
    return f"{clean}/low.webp", f"{clean}/high.webp"


@router.get("", response_model=PaginatedCardsResponse)
def list_cards(
    name: str | None = Query(
        None, description="Case-insensitive partial match against card name"
    ),
    number: str | None = Query(
        None, description="Exact match against card local number"
    ),
    set_id: int | None = Query(None, description="Internal set ID filter"),
    language: str | None = Query(None, description="Card language code"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(24, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> PaginatedCardsResponse:
    """Search and filter locally imported cards. Never makes external calls."""
    query = select(Card).options(joinedload(Card.set))

    if name:
        stripped_name = name.strip()
        # Treat input literally, escaping SQL wildcards
        escaped_name = (
            stripped_name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        query = query.where(Card.name.ilike(f"%{escaped_name}%"))

    if number:
        query = query.where(Card.local_id == number.strip())

    if set_id is not None:
        query = query.where(Card.set_id == set_id)

    if language:
        query = query.where(Card.language == language.lower().strip())

    total_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(total_query) or 0

    # Deterministic ordering: Set ID, number length, number,
    # and unique tie-breaker Card.id
    query = (
        query.order_by(
            Card.set_id.asc(),
            func.length(Card.local_id).asc(),
            Card.local_id.asc(),
            Card.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    card_rows = db.scalars(query).all()
    items = []
    for c in card_rows:
        small_url, large_url = _derive_image_urls(c.image_base_url)
        items.append(
            CardListItem(
                id=c.id,
                source=c.source,
                external_id=c.external_id,
                set_id=c.set_id,
                local_id=c.local_id,
                name=c.name,
                language=c.language,
                image_base_url=c.image_base_url,
                small_image_url=small_url,
                large_image_url=large_url,
                set_name=c.set.name if c.set else None,
            )
        )

    return PaginatedCardsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id}", response_model=CardDetailResponse)
def get_card(id: int, db: Session = Depends(get_db)) -> CardDetailResponse:
    """Retrieve basic local card metadata and set relation without external calls."""
    stmt = select(Card).options(joinedload(Card.set)).where(Card.id == id)
    card = db.scalar(stmt)
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    small_url, large_url = _derive_image_urls(card.image_base_url)
    return CardDetailResponse(
        id=card.id,
        source=card.source,
        external_id=card.external_id,
        set_id=card.set_id,
        local_id=card.local_id,
        name=card.name,
        language=card.language,
        image_base_url=card.image_base_url,
        small_image_url=small_url,
        large_image_url=large_url,
        set=CardSetBrief(
            id=card.set.id,
            external_id=card.set.external_id,
            name=card.set.name,
        ),
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


@router.get("/{id}/details", response_model=CardEnrichmentResponse)
async def get_card_details(
    id: int,
    db: Session = Depends(get_db),
    client: TcgdexClient = Depends(get_tcgdex_client),
) -> CardEnrichmentResponse:
    """Fetch additional on-demand card details via cache or TCGdex."""
    card = db.query(Card).filter(Card.id == id).first()
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")

    source = card.source
    language = card.language
    external_id = card.external_id

    async def fetch_from_tcgdex():
        raw_card = await client.get_card(external_id, language=language)
        if raw_card is None:
            return None
        return map_card_details(raw_card)

    result = await detail_cache.get_or_fetch(
        source=source,
        language=language,
        external_id=external_id,
        fetcher=fetch_from_tcgdex,
    )

    return CardEnrichmentResponse(
        status=result.status,
        source=result.source,
        fetched_at=result.fetched_at,
        details=result.details,
    )
