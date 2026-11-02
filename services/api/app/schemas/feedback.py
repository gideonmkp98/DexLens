from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FeedbackType = Literal[
    "correct_match",
    "wrong_card",
    "in_alternatives",
    "not_found",
    "ocr_incorrect",
    "crop_failed",
    "too_slow",
    "other",
]


class ScanFeedbackCreate(BaseModel):
    feedback_type: FeedbackType
    suggested_card_id: str | None = Field(None, max_length=100)
    selected_card_id: str | None = Field(None, max_length=100)
    confidence_state: str | None = Field(None, max_length=16)
    selected_in_candidates: bool | None = None
    notes: str | None = Field(None, max_length=500)
    device_category: str | None = Field(None, max_length=32)


class ScanFeedbackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str
    user_id: str | None
    anonymous_session_id: str | None
    feedback_type: str
    suggested_card_id: str | None
    selected_card_id: str | None
    confidence_state: str | None
    selected_in_candidates: bool | None
    notes: str | None
    device_category: str | None
    created_at: datetime
