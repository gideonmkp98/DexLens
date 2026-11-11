import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RegistrationMode(StrEnum):
    OPEN = "open"
    BETA_CODE_REQUIRED = "beta_code_required"
    INVITE_ONLY = "invite_only"


class RegistrationStatusResponse(BaseModel):
    registration_mode: str
    allows_open_registration: bool
    requires_code_or_invite: bool


class ValidateBetaCodeRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=64)


class ValidateBetaCodeResponse(BaseModel):
    valid: bool
    label: str | None = None
    message: str | None = None


class ValidateInvitationRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=128)


class ValidateInvitationResponse(BaseModel):
    valid: bool
    masked_email: str | None = None
    message: str | None = None


# --- Admin Schemas ---


class CreateBetaCodeRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=100)
    max_uses: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    allowed_email: str | None = None
    scan_quota_allocated: int | None = Field(default=None, ge=1)
    beta_entitlement: str | None = Field(default=None, max_length=64)
    custom_code: str | None = Field(default=None, min_length=6, max_length=64)

    @field_validator("allowed_email")
    @classmethod
    def clean_allowed_email(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip().lower()
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", clean):
            raise ValueError("Ongeldig e-mailadres voor bètacode restrictie")
        return clean


class BetaCodeCreatedResponse(BaseModel):
    """Returned once upon code creation. Exposes the plaintext code only at creation."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str  # Plaintext code returned once to creator
    code_prefix: str
    label: str
    is_active: bool
    max_uses: int | None
    used_count: int
    allowed_email: str | None
    scan_quota_allocated: int | None
    beta_entitlement: str | None
    expires_at: datetime | None
    created_at: datetime


class BetaCodeResponse(BaseModel):
    """Safe representation for administrative listing. Never includes full secret."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code_prefix: str
    label: str
    is_active: bool
    max_uses: int | None
    used_count: int
    allowed_email: str | None
    scan_quota_allocated: int | None
    beta_entitlement: str | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None


class BetaCodeRedemptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    redeemed_at: datetime
    ip_hash: str | None


class BetaCodeDetailResponse(BetaCodeResponse):
    redemptions: list[BetaCodeRedemptionResponse] = []


class CreateInvitationRequest(BaseModel):
    email: str
    expires_in_days: int | None = Field(default=None, ge=1, le=90)
    scan_quota_allocated: int | None = Field(default=None, ge=1)
    beta_entitlement: str | None = Field(default=None, max_length=64)

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", clean):
            raise ValueError("Ongeldig e-mailadres voor uitnodiging")
        return clean


class InvitationResponse(BaseModel):
    """Administrative representation of personal invitation. Token is NEVER leaked."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    status: str
    expires_at: datetime
    sent_at: datetime
    resend_count: int
    scan_quota_allocated: int | None
    beta_entitlement: str | None
    accepted_by_user_id: str | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class InvitationDetailResponse(InvitationResponse):
    pass


class UpdateRegistrationModeRequest(BaseModel):
    registration_mode: RegistrationMode
