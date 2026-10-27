from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.card_detector import CropCorners, Point


class FieldEvidenceModel(BaseModel):
    """Field-specific extraction evidence, alternatives, and confidence level."""

    model_config = ConfigDict(from_attributes=True)

    raw_text: str | None = Field(
        default=None, description="Raw OCR text observed for this field"
    )
    normalized: str | None = Field(default=None, description="Normalized field value")
    confidence_level: str = Field(
        default="medium",
        description="Field confidence level: 'high', 'medium', 'low', or 'uncertain'",
    )
    source_region: str | None = Field(
        default=None, description="Image region of origin"
    )
    alternatives: list[str] = Field(
        default_factory=list, description="Alternative hypotheses"
    )


class ImageQualityModel(BaseModel):
    """Image resolution and quality assessment for OCR readability."""

    model_config = ConfigDict(from_attributes=True)

    width: int = Field(description="Crop width in pixels")
    height: int = Field(description="Crop height in pixels")
    is_low_res: bool = Field(
        default=False, description="Whether the crop has low resolution"
    )
    warning: str | None = Field(
        default=None, description="Warning message if quality is degraded"
    )
    guidance: str | None = Field(
        default=None, description="Practical recovery guidance for user"
    )


class RecognitionEvidenceModel(BaseModel):
    """Structured provenance and evidence for all recognized card fields."""

    model_config = ConfigDict(from_attributes=True)

    name: FieldEvidenceModel = Field(description="Card name evidence")
    number: FieldEvidenceModel = Field(description="Collector number evidence")
    denominator: FieldEvidenceModel = Field(description="Denominator evidence")
    set_info: FieldEvidenceModel = Field(description="Set code or set ID evidence")
    image_quality: ImageQualityModel = Field(description="Image resolution quality")
    hp: str | None = Field(default=None, description="Extracted HP value")
    attacks: list[str] = Field(
        default_factory=list, description="Extracted attack names"
    )
    abilities: list[str] = Field(
        default_factory=list, description="Extracted ability names"
    )


class ScanResponse(BaseModel):
    """Pydantic schema representing scan metadata and crop status."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="Unique scan UUID")
    status: str = Field(description="Scan processing status, e.g. 'uploaded'")
    image_url: str = Field(
        description="Relative endpoint URL to retrieve the normalized image"
    )
    width: int = Field(description="Stored image width in pixels")
    height: int = Field(description="Stored image height in pixels")
    content_type: str = Field(description="MIME type of stored image")
    file_size: int = Field(description="Size in bytes of stored image file")
    created_at: datetime = Field(description="UTC timestamp when scan was created")
    expires_at: datetime = Field(description="UTC timestamp when scan and file expire")

    # Phase 4 fields
    crop_status: str = Field(
        default="none",
        description="Crop status: 'none', 'detected', 'preview', or 'confirmed'",
    )
    corners: CropCorners | None = Field(
        default=None,
        description="Corner coordinates for current detection or crop",
    )
    rotation: int = Field(
        default=0,
        description="Clockwise rotation in degrees: 0, 90, 180, or 270",
    )
    crop_image_url: str | None = Field(
        default=None,
        description="Relative endpoint URL to retrieve the cropped image",
    )
    crop_width: int | None = Field(
        default=None,
        description="Cropped image width in pixels",
    )
    crop_height: int | None = Field(
        default=None,
        description="Cropped image height in pixels",
    )
    crop_file_size: int | None = Field(
        default=None,
        description="Cropped image file size in bytes",
    )
    crop_version: int = Field(
        default=0,
        description="Monotonically incrementing crop version counter",
    )
    confirmed_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when crop was confirmed by user",
    )

    # Phase 5 fields
    recognition_status: str = Field(
        default="none",
        description=(
            "Recognition status: 'none', 'processing', 'completed', or 'failed'"
        ),
    )
    recognition_id: str | None = Field(
        default=None,
        description="UUID of current recognition run",
    )
    ocr_crop_version: int | None = Field(
        default=None,
        description="Crop version analyzed during OCR",
    )
    ocr_raw_text: str | None = Field(
        default=None,
        description="Raw unnormalized OCR extracted text",
    )
    recognized_name: str | None = Field(
        default=None,
        description="Normalized recognized card name",
    )
    recognized_number: str | None = Field(
        default=None,
        description="Normalized recognized collector number",
    )
    recognized_set_code: str | None = Field(
        default=None,
        description="Recognized set code or abbreviation",
    )
    ocr_confidence: float | None = Field(
        default=None,
        description="Average OCR engine character/word confidence (0.0 to 100.0)",
    )
    confidence_state: str = Field(
        default="medium",
        description="Recognition confidence tier: 'high', 'medium', or 'low'",
    )
    image_quality: ImageQualityModel | None = Field(
        default=None,
        description="Image quality assessment",
    )
    evidence: RecognitionEvidenceModel | None = Field(
        default=None,
        description="Structured per-field evidence",
    )
    search_version: int = Field(
        default=0,
        description="Candidate search version counter",
    )
    candidate_search_version: int = Field(
        default=0,
        description="Alias for search_version",
    )
    card_selection_version: int = Field(
        default=0,
        description="Card selection version counter",
    )
    catalog_status: str = Field(
        default="none",
        description="Catalog retrieval status: 'none', 'ok', or 'unavailable'",
    )
    catalog_error: str | None = Field(
        default=None,
        description="Catalog error message if unavailable",
    )
    user_search_name: str | None = Field(
        default=None,
        description="User-edited card name query",
    )
    user_search_number: str | None = Field(
        default=None,
        description="User-edited collector number query",
    )
    user_search_set_code: str | None = Field(
        default=None,
        description="User-edited printed set code query",
    )
    user_search_provider_set_id: str | None = Field(
        default=None,
        description="User-edited provider set ID query",
    )
    candidates: list["CandidateMatchItem"] | None = Field(
        default=None,
        description="Top catalog candidate matches",
    )
    confirmed_card: "ConfirmedCardInfo | None" = Field(
        default=None,
        description="User-confirmed catalog card details",
    )


class CandidateMatchItem(BaseModel):
    """Plausible card catalog match candidate."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="External card identifier (e.g. 'base1-58')")
    name: str = Field(description="Card name")
    local_id: str = Field(description="Collector number within set")
    set_id: str = Field(description="External set identifier")
    set_name: str = Field(description="Set name")
    image_url: str | None = Field(default=None, description="Card image thumbnail URL")
    score: int = Field(
        ge=0, le=100, description="Heuristic match ranking score (0-100)"
    )
    reasons: list[str] = Field(
        default_factory=list, description="Explanations for the match score"
    )
    hp: str | None = Field(default=None, description="Card HP from catalog")
    matched_attacks: list[str] = Field(
        default_factory=list, description="Candidate attacks matching OCR"
    )
    matched_abilities: list[str] = Field(
        default_factory=list, description="Candidate abilities matching OCR"
    )
    visual_similarity: float | None = Field(
        default=None, description="Visual artwork similarity score"
    )


class ConfirmedCardInfo(BaseModel):
    """Details of a user-confirmed card selection."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="External card identifier (e.g. 'base1-58')")
    name: str = Field(description="Card name")
    set_name: str = Field(description="Set name")
    number: str = Field(description="Collector number")
    image_url: str | None = Field(default=None, description="Card image thumbnail URL")
    confirmed_at: datetime = Field(description="UTC timestamp when card was confirmed")


class RecognizeResponse(BaseModel):
    """Result of card OCR recognition and initial catalog candidate matching."""

    recognition_id: str = Field(description="Unique recognition run UUID")
    crop_version: int = Field(description="Crop version that was analyzed")
    raw_text: str = Field(description="Raw OCR output text")
    recognized_name: str | None = Field(default=None, description="Extracted card name")
    recognized_number: str | None = Field(
        default=None, description="Extracted collector number"
    )
    recognized_set_code: str | None = Field(
        default=None, description="Extracted set code"
    )
    ocr_confidence: float = Field(default=0.0, description="OCR confidence score")
    confidence_state: str = Field(
        default="medium",
        description="Recognition confidence tier: 'high', 'medium', or 'low'",
    )
    image_quality: ImageQualityModel | None = Field(
        default=None,
        description="Image quality assessment",
    )
    evidence: RecognitionEvidenceModel | None = Field(
        default=None,
        description="Structured per-field evidence",
    )
    catalog_status: str = Field(
        default="ok",
        description="Catalog lookup status: 'ok' or 'unavailable'",
    )
    catalog_error: str | None = Field(
        default=None,
        description="Catalog error explanation if lookup failed",
    )
    search_version: int = Field(
        default=0,
        description="Search version when recognition completed",
    )
    card_selection_version: int = Field(
        default=0,
        description="Current card selection version",
    )
    candidates: list[CandidateMatchItem] = Field(
        default_factory=list, description="Top catalog matches"
    )
    total_candidates: int = Field(
        default=0, description="Total matching candidates found"
    )


class SearchCandidatesRequest(BaseModel):
    """Payload to query catalog candidates with user-edited search parameters."""

    name: str | None = Field(default=None, description="Card name filter")
    number: str | None = Field(default=None, description="Collector number filter")
    set_id: str | None = Field(default=None, description="Set identifier filter")
    set_code: str | None = Field(default=None, description="Printed set code filter")
    expected_crop_version: int = Field(
        ge=0, description="Current confirmed crop version"
    )
    expected_search_version: int | None = Field(
        default=None,
        ge=0,
        description="Current search version to prevent race conditions",
    )


class SearchCandidatesResponse(BaseModel):
    """Response containing updated catalog candidates from user search query."""

    search_version: int = Field(description="Monotonically incrementing search version")
    crop_version: int = Field(description="Crop version that search is bound to")
    confidence_state: str = Field(
        default="medium",
        description="Recognition confidence tier: 'high', 'medium', or 'low'",
    )
    catalog_status: str = Field(
        default="ok",
        description="Catalog query status: 'ok' or 'unavailable'",
    )
    candidates: list[CandidateMatchItem] = Field(
        default_factory=list, description="Ranked candidates"
    )
    total_candidates: int = Field(
        default=0, description="Total matching candidates found"
    )


class ConfirmCardRequest(BaseModel):
    """Request payload to explicitly confirm a catalog card match."""

    card_id: str = Field(
        min_length=1, max_length=100, description="Selected catalog card ID"
    )
    expected_crop_version: int = Field(
        ge=0, description="Current confirmed crop version"
    )
    expected_search_version: int | None = Field(
        default=None,
        ge=0,
        description="Search version of candidate list viewed when confirming",
    )
    expected_selection_version: int | None = Field(
        default=None,
        ge=0,
        description="Expected card selection version to prevent stale overrides",
    )


class ResetCardConfirmationRequest(BaseModel):
    """Request payload to clear confirmed card selection while preserving crop."""

    expected_crop_version: int = Field(
        ge=0, description="Current confirmed crop version"
    )
    expected_selection_version: int | None = Field(
        default=None,
        ge=0,
        description="Expected card selection version to prevent stale overrides",
    )


class DetectResponse(BaseModel):
    """Result of automatic card corner detection."""

    detected: bool = Field(description="Whether a plausible card was detected")
    corners: CropCorners = Field(description="4 detected or fallback corner points")
    message: str = Field(description="Descriptive explanation of the detection outcome")
    score: float = Field(
        description="Heuristic quality score between 0.0 and 1.0 (not a probability)"
    )


class CropRequest(BaseModel):
    """Request payload to generate a perspective-corrected crop."""

    corners: CropCorners = Field(
        description="4 corner points in normalized coordinates"
    )
    rotation: int = Field(
        default=0,
        description="Clockwise rotation in degrees (must be 0, 90, 180, or 270)",
    )
    expected_version: int = Field(
        ge=0,
        description="Expected current crop_version for atomic concurrency control",
    )


class ConfirmCropRequest(BaseModel):
    """Request payload to confirm the current previewed crop."""

    crop_version: int = Field(
        description="The specific crop version to confirm against race conditions"
    )


class ErrorDetail(BaseModel):
    """Structured error details for consistent machine-readable contracts."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Top-level error response model."""

    detail: ErrorDetail


__all__ = [
    "CandidateMatchItem",
    "ConfirmCardRequest",
    "ConfirmCropRequest",
    "ConfirmedCardInfo",
    "CropCorners",
    "CropRequest",
    "DetectResponse",
    "ErrorDetail",
    "ErrorResponse",
    "Point",
    "RecognizeResponse",
    "ResetCardConfirmationRequest",
    "ScanResponse",
    "SearchCandidatesRequest",
    "SearchCandidatesResponse",
]
