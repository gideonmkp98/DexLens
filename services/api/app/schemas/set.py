from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SetBase(BaseModel):
    id: int
    source: str
    external_id: str
    name: str
    language: str
    series: str | None = None
    logo_url: str | None = None
    symbol_url: str | None = None
    release_date: str | None = None
    printed_total: int | None = None
    total: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SetSummaryResponse(SetBase):
    local_card_count: int = 0


class SetDetailResponse(SetBase):
    local_card_count: int = 0


class PaginatedSetsResponse(BaseModel):
    items: list[SetSummaryResponse]
    total: int
    page: int
    page_size: int
