import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.collection import (
    CollectionCreateRequest,
    CollectionItemResponse,
    CollectionListResponse,
    CollectionStatsResponse,
    CollectionUpdateRequest,
)
from app.services.card_catalog import CardCatalogService, get_card_catalog_service
from app.services.collection import (
    CollectionItemNotFoundError,
    CollectionService,
    ConcurrencyConflictError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/collection", tags=["Collection"])


def _get_collection_service(
    db: Session = Depends(get_db),
    catalog_service: CardCatalogService = Depends(get_card_catalog_service),
) -> CollectionService:
    return CollectionService(db=db, catalog_service=catalog_service)


@router.get("", response_model=CollectionListResponse)
async def list_collection(
    query: str | None = Query(
        None, description="Search term for card name, number, set name, or notes"
    ),
    set_id: str | None = Query(None, description="Filter by set ID"),
    condition: str | None = Query(None, description="Filter by condition grade"),
    language: str | None = Query(None, description="Filter by card language code"),
    variant: str | None = Query(None, description="Filter by variant"),
    sort: str = Query(
        "recent",
        description=(
            "Sort order: 'recent', 'name_asc', 'name_desc', "
            "'set_asc', 'number_asc', 'quantity_desc'"
        ),
    ),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(24, ge=1, le=100, description="Items per page"),
    service: CollectionService = Depends(_get_collection_service),
) -> CollectionListResponse:
    """Retrieve personal collection items with filtering, sorting, and pagination."""
    items, total, has_more = await service.list_items(
        query=query,
        set_id=set_id,
        condition=condition,
        language=language,
        variant=variant,
        sort=sort,
        page=page,
        page_size=page_size,
    )

    return CollectionListResponse(
        items=[CollectionItemResponse.model_validate(it) for it in items],
        total=total,
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.post(
    "",
    response_model=CollectionItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_collection_item(
    body: CollectionCreateRequest,
    service: CollectionService = Depends(_get_collection_service),
) -> CollectionItemResponse:
    """Manually add a card specimen to personal collection."""
    try:
        item = await service.create_item(body)
        return CollectionItemResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_ITEM_DATA", "message": str(e)},
        ) from e


@router.get("/stats", response_model=CollectionStatsResponse)
async def get_collection_stats(
    service: CollectionService = Depends(_get_collection_service),
) -> CollectionStatsResponse:
    """Retrieve aggregated collection summary metrics and distribution stats."""
    return await service.get_stats()


@router.get("/{entry_id}", response_model=CollectionItemResponse)
async def get_collection_item(
    entry_id: str,
    service: CollectionService = Depends(_get_collection_service),
) -> CollectionItemResponse:
    """Retrieve single collection item by UUID."""
    item = await service.get_item(entry_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ITEM_NOT_FOUND",
                "message": f"Collection item '{entry_id}' not found.",
            },
        )
    return CollectionItemResponse.model_validate(item)


@router.patch("/{entry_id}", response_model=CollectionItemResponse)
async def update_collection_item(
    entry_id: str,
    body: CollectionUpdateRequest,
    service: CollectionService = Depends(_get_collection_service),
) -> CollectionItemResponse:
    """Update editable attributes of a collection item with optimistic concurrency."""
    try:
        updated = await service.update_item(entry_id, body)
        return CollectionItemResponse.model_validate(updated)
    except CollectionItemNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "ITEM_NOT_FOUND", "message": str(e)},
        ) from e
    except ConcurrencyConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": e.message,
                "current_version": e.current_version,
            },
        ) from e
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_VALUE", "message": str(e)},
        ) from e


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection_item(
    entry_id: str,
    service: CollectionService = Depends(_get_collection_service),
) -> Response:
    """Remove a card specimen from personal collection."""
    deleted = await service.delete_item(entry_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "ITEM_NOT_FOUND",
                "message": f"Collection item '{entry_id}' not found.",
            },
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
