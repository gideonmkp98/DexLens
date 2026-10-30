from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Allowed domain value literals
CollectionCondition = Literal[
    "mint",
    "near_mint",
    "lightly_played",
    "moderately_played",
    "heavily_played",
    "damaged",
]

CollectionVariant = Literal[
    "normal",
    "holo",
    "reverse_holo",
    "first_edition",
    "promo",
    "masterball",
    "pokeball",
]

ALLOWED_CONDITIONS: list[str] = [
    "mint",
    "near_mint",
    "lightly_played",
    "moderately_played",
    "heavily_played",
    "damaged",
]

ALLOWED_VARIANTS: list[str] = [
    "normal",
    "holo",
    "reverse_holo",
    "first_edition",
    "promo",
    "masterball",
    "pokeball",
]


class CollectionItemResponse(BaseModel):
    """Full representation of a personal collection item with immutable snapshots."""

    id: str = Field(description="Unique UUID primary key")
    card_id: str = Field(description="External card identifier (e.g. 'base1-58')")
    provider: str = Field(default="tcgdex", description="Catalog provider key")
    card_name: str = Field(description="Card name snapshot")
    set_id: str = Field(description="Set identifier snapshot")
    set_name: str = Field(description="Set name snapshot")
    collector_number: str = Field(description="Collector number within set")
    card_image_url: str | None = Field(
        default=None, description="Card image URL snapshot"
    )
    quantity: int = Field(ge=1, description="Quantity owned (>= 1)")
    language: str = Field(description="Card language code")
    variant: CollectionVariant = Field(description="Printing variant")
    condition: CollectionCondition = Field(description="Specimen condition grade")
    notes: str | None = Field(default=None, description="Collector notes")
    purchase_price: Decimal | None = Field(
        default=None, description="Acquisition purchase price"
    )
    currency: str | None = Field(
        default=None, description="3-letter uppercase ISO currency code"
    )
    acquired_at: date | None = Field(
        default=None, description="Date specimen was acquired"
    )
    source_scan_id: str | None = Field(
        default=None, description="Source scan UUID if added via scanning flow"
    )
    version: int = Field(ge=1, description="Optimistic concurrency version")
    created_at: datetime = Field(description="Timestamp when created")
    updated_at: datetime = Field(description="Timestamp when last updated")

    model_config = ConfigDict(from_attributes=True)


class CollectionListResponse(BaseModel):
    """Paginated collection list response."""

    items: list[CollectionItemResponse] = Field(description="List of collection items")
    total: int = Field(ge=0, description="Total matching items count")
    page: int = Field(ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(ge=1, description="Items per page")
    has_more: bool = Field(description="True if more pages exist")


class CollectionCreateRequest(BaseModel):
    """Payload for manually creating a personal collection item."""

    card_id: str = Field(
        min_length=1, max_length=100, description="External card identifier"
    )
    provider: str = Field(
        default="tcgdex", max_length=32, description="Catalog provider"
    )
    card_name: str | None = Field(
        default=None, max_length=255, description="Card name snapshot override"
    )
    set_id: str | None = Field(
        default=None, max_length=50, description="Set ID snapshot override"
    )
    set_name: str | None = Field(
        default=None, max_length=255, description="Set name snapshot override"
    )
    collector_number: str | None = Field(
        default=None, max_length=50, description="Collector number snapshot override"
    )
    card_image_url: str | None = Field(
        default=None, max_length=512, description="Card image URL snapshot"
    )
    quantity: int = Field(default=1, ge=1, description="Quantity owned (>= 1)")
    language: str = Field(
        default="en", min_length=2, max_length=10, description="Language code"
    )
    variant: CollectionVariant = Field(default="normal", description="Printing variant")
    condition: CollectionCondition = Field(
        default="near_mint", description="Specimen condition"
    )
    notes: str | None = Field(default=None, description="Collector notes")
    purchase_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Purchase price",
    )
    currency: str | None = Field(
        default=None, description="3-letter uppercase ISO currency code"
    )
    acquired_at: date | None = Field(default=None, description="Acquisition date")
    source_scan_id: str | None = Field(
        default=None, max_length=36, description="Optional scan UUID origin"
    )

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            clean = v.strip().upper()
            if len(clean) != 3 or not clean.isalpha():
                raise ValueError(
                    "Currency must be a 3-letter uppercase ISO code (e.g. 'EUR', 'USD')"
                )
            return clean
        raise ValueError("Invalid currency format")

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Any) -> Any:
        if isinstance(v, str):
            clean = v.strip().lower()
            if not (2 <= len(clean) <= 10 and clean.isalpha()):
                raise ValueError(
                    "Language must be a standard code (e.g. 'en', 'ja', 'fr')"
                )
            return clean
        return v


class CollectionUpdateRequest(BaseModel):
    """Payload for updating an existing collection item."""

    quantity: int | None = Field(
        default=None, ge=1, description="Quantity owned (>= 1)"
    )
    condition: CollectionCondition | None = Field(
        default=None, description="Specimen condition grade"
    )
    variant: CollectionVariant | None = Field(
        default=None, description="Printing variant"
    )
    notes: str | None = Field(default=None, description="Collector notes")
    purchase_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Purchase price",
    )
    currency: str | None = Field(
        default=None, description="3-letter uppercase ISO currency code"
    )
    acquired_at: date | None = Field(default=None, description="Acquisition date")
    expected_version: int = Field(
        ge=1,
        description=(
            "Explicit expected version required for atomic optimistic concurrency"
        ),
    )

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            clean = v.strip().upper()
            if len(clean) != 3 or not clean.isalpha():
                raise ValueError(
                    "Currency must be a 3-letter uppercase ISO code (e.g. 'EUR', 'USD')"
                )
            return clean
        raise ValueError("Invalid currency format")


class CollectionSetDistributionItem(BaseModel):
    """Breakdown of cards owned in a specific set."""

    set_id: str = Field(description="Set identifier")
    set_name: str = Field(description="Set name")
    count: int = Field(description="Number of unique cards owned in this set")
    total_cards: int = Field(
        description="Total cards count (sum of quantities) in this set"
    )


class CollectionStatsResponse(BaseModel):
    """Aggregated personal collection analytics."""

    total_cards: int = Field(description="Total cards owned (sum of all quantities)")
    unique_cards: int = Field(description="Count of distinct collection item records")
    total_sets: int = Field(description="Count of distinct sets represented")
    duplicate_count: int = Field(
        description="Total duplicates owned (sum of max(0, quantity - 1))"
    )
    condition_distribution: dict[str, int] = Field(
        description="Distribution count of collection items by condition"
    )
    set_distribution: list[CollectionSetDistributionItem] = Field(
        description="Top sets distribution by card count"
    )
    recent_additions: list[CollectionItemResponse] = Field(
        description="Recent items added to the collection"
    )


class AddFromScanRequest(BaseModel):
    """Optional overrides when saving a verified scan card into the collection."""

    condition: CollectionCondition = Field(
        default="near_mint", description="Specimen condition tier"
    )
    variant: CollectionVariant = Field(
        default="normal", description="Card printing variant"
    )
    quantity: int = Field(default=1, ge=1, description="Quantity to add (>= 1)")
    notes: str | None = Field(default=None, description="Collector notes")
    purchase_price: Decimal | None = Field(
        default=None,
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Purchase price",
    )
    currency: str | None = Field(
        default=None, description="3-letter uppercase ISO currency code"
    )
    acquired_at: date | None = Field(default=None, description="Acquisition date")

    @field_validator("currency", mode="before")
    @classmethod
    def validate_currency(cls, v: Any) -> Any:
        if v is None:
            return None
        if isinstance(v, str):
            clean = v.strip().upper()
            if len(clean) != 3 or not clean.isalpha():
                raise ValueError(
                    "Currency must be a 3-letter uppercase ISO code (e.g. 'EUR', 'USD')"
                )
            return clean
        raise ValueError("Invalid currency format")
