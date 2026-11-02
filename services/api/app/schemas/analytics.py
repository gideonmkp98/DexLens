import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

APPROVED_PRODUCT_EVENTS: set[str] = {
    "scan_started",
    "camera_permission_granted",
    "camera_permission_denied",
    "capture_mode_changed",
    "auto_capture_triggered",
    "manual_capture_triggered",
    "upload_started",
    "upload_completed",
    "scan_processing_started",
    "scan_processing_completed",
    "scan_processing_failed",
    "no_card_detected",
    "no_catalog_candidates",
    "candidate_list_shown",
    "candidate_selected",
    "top_candidate_corrected",
    "card_confirmed",
    "card_added_to_collection",
    "scan_abandoned",
    "user_feedback_submitted",
}

FORBIDDEN_METADATA_KEYS: set[str] = {
    "image",
    "photo",
    "raw_photo",
    "raw_image",
    "ocr_text",
    "raw_text",
    "ocr",
    "base64",
    "picture",
    "frame",
}

APPROVED_METADATA_KEYS: set[str] = {
    "original_card_id",
    "corrected_card_id",
    "feedback_type",
}


class ProductAnalyticsEventCreate(BaseModel):
    event_name: str
    schema_version: int = 1
    session_id: str | None = None
    scan_id: str | None = None
    timestamp: datetime | None = None
    capture_mode: Literal["auto", "manual", "upload"] | None = None
    device_category: Literal["mobile", "tablet", "desktop"] | None = None
    browser_category: (
        Literal["safari_ios", "chrome_android", "chrome_desktop", "firefox", "other"]
        | None
    ) = None
    viewport_category: Literal["compact", "standard", "wide"] | None = None
    processing_duration_ms: int | None = Field(None, ge=0)
    confidence_state: Literal["high", "medium", "low", "none"] | None = None
    candidate_count: int | None = Field(None, ge=0)
    is_top_suggestion_selected: bool | None = None
    failure_category: str | None = Field(
        None, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$"
    )
    metadata: dict[str, Any] | None = None

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in APPROVED_PRODUCT_EVENTS:
            raise ValueError(f"Event '{clean}' is not an approved product event")
        return clean

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is None:
            return None

        # Check for forbidden privacy-violating keys
        for key in v:
            lower_k = key.lower()
            if lower_k not in APPROVED_METADATA_KEYS:
                raise ValueError(f"Metadata key '{key}' is not allowlisted")
            if any(forbidden in lower_k for forbidden in FORBIDDEN_METADATA_KEYS):
                raise ValueError(
                    f"Privacy violation: metadata key '{key}' "
                    "contains forbidden telemetry term"
                )

        # Check for forbidden base64 strings or images in values
        if any(
            not isinstance(value, (str, int, float, bool, type(None)))
            for value in v.values()
        ):
            raise ValueError("Metadata values must be primitive values")
        if any(isinstance(value, str) and len(value) > 128 for value in v.values()):
            raise ValueError("Metadata string values may not exceed 128 characters")

        serialized = json.dumps(v)
        if len(serialized.encode("utf-8")) > 2048:
            raise ValueError("Metadata payload exceeds 2048 byte ceiling")

        if "data:image" in serialized or "base64" in serialized:
            raise ValueError(
                "Privacy violation: raw image/base64 data detected in metadata"
            )

        return v


class AnalyticsEventResponse(BaseModel):
    id: str
    event_name: str
    created_at: datetime


class PilotSummaryMetrics(BaseModel):
    total_scans: int
    completion_rate: float
    top_candidate_acceptance_rate: float
    candidate_correction_rate: float
    processing_duration_median_ms: float | None
    processing_duration_p95_ms: float | None
    capture_mode_distribution: dict[str, int]
    failure_categories: dict[str, int]
    total_feedback_count: int
    feedback_breakdown: dict[str, int]
