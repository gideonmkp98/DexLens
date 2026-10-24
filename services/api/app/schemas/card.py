from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CardSetBrief(BaseModel):
    id: int | str | None = None
    external_id: str | None = None
    name: str

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "external_id" not in data and "id" in data and data["id"] is not None:
                data["external_id"] = str(data["id"])
            elif (
                "id" not in data
                and "external_id" in data
                and data["external_id"] is not None
            ):
                data["id"] = data["external_id"]
        return data


class CardListItem(BaseModel):
    id: int | str | None = None
    source: str = "tcgdex"
    external_id: str
    set_id: str
    local_id: str
    name: str
    language: str = "en"
    image_base_url: str | None = None
    small_image_url: str | None = None
    large_image_url: str | None = None
    set_name: str | None = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("set_id", mode="before")
    @classmethod
    def coerce_set_id(cls, v: Any) -> Any:
        if v is not None and not isinstance(v, str):
            return str(v)
        return v


class CardDetailResponse(BaseModel):
    id: int | str | None = None
    source: str = "tcgdex"
    external_id: str
    set_id: str | None = None
    local_id: str
    name: str
    language: str = "en"
    small_image_url: str | None = None
    large_image_url: str | None = None
    image_base_url: str | None = None
    set: CardSetBrief | None = None
    status: str = "available"
    category: str | None = None
    illustrator: str | None = None
    rarity: str | None = None
    hp: int | None = None
    types: list[str] | None = None
    regulation_mark: str | None = Field(default=None, alias="regulationMark")
    variants: dict[str, Any] | None = None
    attacks: list[dict[str, Any]] | None = None
    abilities: list[dict[str, Any]] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("set_id", mode="before")
    @classmethod
    def coerce_set_id(cls, v: Any) -> Any:
        if v is not None and not isinstance(v, str):
            return str(v)
        return v


class PaginatedCardsResponse(BaseModel):
    items: list[CardListItem]
    total: int | None = None
    page: int
    page_size: int
    has_more: bool = False


class CardEnrichmentResponse(BaseModel):
    status: str  # "available", "stale", "unavailable"
    source: str
    fetched_at: datetime | None = None
    details: dict[str, Any] | None = None
