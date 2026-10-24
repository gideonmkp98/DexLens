from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CardSetBrief(BaseModel):
    id: int
    external_id: str
    name: str

    model_config = ConfigDict(from_attributes=True)


class CardListItem(BaseModel):
    id: int
    source: str
    external_id: str
    set_id: int
    local_id: str
    name: str
    language: str
    image_base_url: str | None = None
    small_image_url: str | None = None
    large_image_url: str | None = None
    set_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class CardDetailResponse(BaseModel):
    id: int
    source: str
    external_id: str
    set_id: int
    local_id: str
    name: str
    language: str
    image_base_url: str | None = None
    small_image_url: str | None = None
    large_image_url: str | None = None
    set: CardSetBrief
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedCardsResponse(BaseModel):
    items: list[CardListItem]
    total: int
    page: int
    page_size: int


class CardEnrichmentResponse(BaseModel):
    status: str  # "available", "stale", "unavailable"
    source: str
    fetched_at: datetime | None = None
    details: dict[str, Any] | None = None
