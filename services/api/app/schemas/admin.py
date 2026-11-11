from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class AdminUserItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    status: str
    is_active: bool
    verification_status: str
    scan_quota_override: int | None = None
    created_at: datetime
    updated_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserItem]
    total: int
    limit: int
    offset: int


class AdminUserDetailsResponse(BaseModel):
    id: str
    email: str
    role: str
    status: str
    is_active: bool
    verification_status: str
    scan_quota_override: int | None = None
    created_at: datetime
    updated_at: datetime
    scans_count: int
    active_sessions_count: int
    collection_items_count: int
    quota: dict[str, Any]
    recent_audit_events: list[dict[str, Any]]


class UpdateUserStatusRequest(BaseModel):
    status: str
    reason: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        clean = v.strip().lower()
        if clean not in ("active", "suspended", "blocked"):
            raise ValueError("Status moet 'active', 'suspended' of 'blocked' zijn.")
        return clean

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 3:
            raise ValueError("Toelichting moet minimaal 3 tekens bevatten.")
        return clean


class UpdateUserQuotaRequest(BaseModel):
    scan_quota_override: int | None = None
    reason: str

    @field_validator("scan_quota_override")
    @classmethod
    def validate_quota(cls, v: int | None) -> int | None:
        if v is not None and v < 0:
            raise ValueError("Scan-quota kan niet negatief zijn.")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 3:
            raise ValueError("Toelichting moet minimaal 3 tekens bevatten.")
        return clean


class GlobalQuotaResponse(BaseModel):
    daily_scan_limit: int
    hourly_scan_limit: int
    updated_at: datetime | None = None


class UpdateGlobalQuotaRequest(BaseModel):
    daily_scan_limit: int
    hourly_scan_limit: int
    reason: str

    @field_validator("daily_scan_limit", "hourly_scan_limit")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Limiet moet groter zijn dan 0.")
        return v

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 3:
            raise ValueError("Toelichting moet minimaal 3 tekens bevatten.")
        return clean


class BetaCodeResponse(BaseModel):
    id: str
    code: str
    code_prefix: str
    label: str | None = None
    invitation_email: str | None = None
    max_uses: int
    used_count: int
    status: str
    expires_at: datetime | None = None
    created_at: datetime
    created_by_user_id: str | None = None


class BetaCodeListResponse(BaseModel):
    items: list[BetaCodeResponse]
    total: int
    limit: int
    offset: int


class CreateBetaCodeRequest(BaseModel):
    code: str | None = None
    label: str | None = None
    invitation_email: str | None = None
    max_uses: int = 1
    expires_days: int | None = None

    @field_validator("max_uses")
    @classmethod
    def validate_max_uses(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Aantal keren te gebruiken moet groter zijn dan 0.")
        return v


class RevokeBetaCodeRequest(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def validate_reason(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 3:
            raise ValueError("Toelichting moet minimaal 3 tekens bevatten.")
        return clean


class AuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: str | None = None
    actor_email: str | None = None
    action: str
    target_type: str
    target_id: str | None = None
    metadata_json: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    limit: int
    offset: int


class AbuseStatusResponse(BaseModel):
    turnstile_enabled: bool
    site_key: str | None = None
    burst_threshold_anonymous: int
    burst_threshold_authenticated: int
    hard_rate_limit: int
