from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.scan import (
    CandidateMatchItem,
    ConfirmedCardInfo,
    CropCorners,
    ScanResponse,
)


class ScanSessionCreateRequest(BaseModel):
    """Request payload to create a new scan session."""

    model_config = ConfigDict(extra="ignore")


class ScanSessionResponse(BaseModel):
    """Basic response for a scan session."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique scan session UUID")
    status: str = Field(
        description="Session status: 'active', 'completed', or 'abandoned'"
    )
    created_at: datetime = Field(description="Session creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    completed_at: datetime | None = Field(
        default=None, description="Completion timestamp"
    )
    total_scans: int = Field(default=0, description="Total number of scans in session")


class ScanSessionItemResponse(BaseModel):
    """Scanned card details within a session."""

    model_config = ConfigDict(from_attributes=True)

    scan_id: str = Field(description="Unique scan UUID")
    session_id: str | None = Field(default=None, description="Scan session UUID")
    status: str = Field(description="Scan processing status")
    crop_status: str = Field(description="Crop status")
    created_at: datetime = Field(description="Scan creation timestamp")
    image_url: str = Field(description="URL to access normalized scan image")
    crop_image_url: str | None = Field(
        default=None, description="URL to access cropped image"
    )
    best_match: CandidateMatchItem | None = Field(
        default=None, description="Top ranked catalog match or confirmed card"
    )
    candidates: list[CandidateMatchItem] = Field(
        default_factory=list, description="Top ranked candidates"
    )
    confirmed_card: ConfirmedCardInfo | None = Field(
        default=None, description="Confirmed card details"
    )
    in_collection: bool = Field(
        default=False, description="Whether this card exists in user's collection"
    )
    collection_quantity: int = Field(
        default=0, description="Total quantity owned in collection"
    )
    collection_item_id: str | None = Field(
        default=None, description="ID of collection item if owned"
    )


class ScanSessionDetailResponse(BaseModel):
    """Comprehensive scan session details including scanned items."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique scan session UUID")
    status: str = Field(
        description="Session status: 'active', 'completed', or 'abandoned'"
    )
    created_at: datetime = Field(description="Session creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    completed_at: datetime | None = Field(
        default=None, description="Completion timestamp"
    )
    total_scans: int = Field(description="Total number of scans in session")
    items: list[ScanSessionItemResponse] = Field(
        default_factory=list, description="Ordered list of scanned cards"
    )


class LiveCaptureResponse(BaseModel):
    """Response returned from a live camera frame capture."""

    model_config = ConfigDict(from_attributes=True)

    scan: ScanResponse = Field(description="The created scan entity and metadata")
    detected: bool = Field(description="Whether a card boundary was detected")
    corners: CropCorners | None = Field(
        default=None, description="Card corner coordinates"
    )
    candidates: list[CandidateMatchItem] = Field(
        default_factory=list, description="Ranked catalog match candidates"
    )
    best_match: CandidateMatchItem | None = Field(
        default=None, description="Top ranked candidate match"
    )
    in_collection: bool = Field(
        default=False, description="Whether top candidate exists in collection"
    )
    collection_quantity: int = Field(
        default=0, description="Quantity owned in collection"
    )
    collection_item_id: str | None = Field(
        default=None, description="Collection item ID if owned"
    )
    session_id: str = Field(description="Scan session UUID")
    session_status: str = Field(description="Current status of the scan session")
