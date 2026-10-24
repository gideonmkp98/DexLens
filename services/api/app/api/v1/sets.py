from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.card import Card
from app.models.set import Set
from app.schemas.set import PaginatedSetsResponse, SetDetailResponse, SetSummaryResponse

router = APIRouter(prefix="/sets", tags=["Sets"])


@router.get("", response_model=PaginatedSetsResponse)
def list_sets(
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(24, ge=1, le=100, description="Items per page"),
    language: str | None = Query(None, description="Optional language filter"),
    db: Session = Depends(get_db),
) -> PaginatedSetsResponse:
    """Retrieve paginated list of locally imported sets with local card counts."""
    base_query = select(Set)
    if language:
        base_query = base_query.where(Set.language == language.lower().strip())

    total_query = select(func.count()).select_from(base_query.subquery())
    total = db.scalar(total_query) or 0

    stmt = select(Set, func.count(Card.id).label("local_card_count")).outerjoin(
        Card, Card.set_id == Set.id
    )
    if language:
        stmt = stmt.where(Set.language == language.lower().strip())

    stmt = (
        stmt.group_by(Set.id)
        .order_by(
            Set.release_date.is_(None),
            Set.release_date.desc(),
            Set.name.asc(),
            Set.id.asc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    rows = db.execute(stmt).all()
    items = [
        SetSummaryResponse(
            id=s.id,
            source=s.source,
            external_id=s.external_id,
            name=s.name,
            language=s.language,
            series=s.series,
            logo_url=s.logo_url,
            symbol_url=s.symbol_url,
            release_date=s.release_date,
            printed_total=s.printed_total,
            total=s.total,
            local_card_count=count,
            created_at=s.created_at,
            updated_at=s.updated_at,
        )
        for s, count in rows
    ]

    return PaginatedSetsResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{id}", response_model=SetDetailResponse)
def get_set(id: int, db: Session = Depends(get_db)) -> SetDetailResponse:
    """Retrieve metadata and local card count for an individual imported set."""
    stmt = (
        select(Set, func.count(Card.id).label("local_card_count"))
        .outerjoin(Card, Card.set_id == Set.id)
        .where(Set.id == id)
        .group_by(Set.id)
    )
    row = db.execute(stmt).first()
    if not row:
        raise HTTPException(status_code=404, detail="Set not found")

    s, count = row
    return SetDetailResponse(
        id=s.id,
        source=s.source,
        external_id=s.external_id,
        name=s.name,
        language=s.language,
        series=s.series,
        logo_url=s.logo_url,
        symbol_url=s.symbol_url,
        release_date=s.release_date,
        printed_total=s.printed_total,
        total=s.total,
        local_card_count=count,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )
