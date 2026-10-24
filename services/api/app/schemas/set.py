from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SetBase(BaseModel):
    id: int | str | None = None
    source: str = "tcgdex"
    external_id: str
    name: str
    language: str = "en"
    series: str | None = None
    logo_url: str | None = None
    symbol_url: str | None = None
    release_date: str | None = None
    printed_total: int | None = None
    total: int | None = None
    card_count: int = 0
    local_card_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SetSummaryResponse(SetBase):
    pass


class SetDetailResponse(SetBase):
    pass


class PaginatedSetsResponse(BaseModel):
    items: list[SetSummaryResponse]
    total: int
    page: int
    page_size: int
    has_more: bool = False
