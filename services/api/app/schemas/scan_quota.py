from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ScanQuotaInfo(BaseModel):
    """Daily scan quota metadata returned by scan operations."""

    model_config = ConfigDict(from_attributes=True)

    limit: int | None = Field(
        default=None,
        description="Daily scan limit in UTC, or null if unlimited",
    )
    used: int = Field(
        default=0,
        description="Number of accepted scans consumed today (UTC)",
    )
    remaining: int | None = Field(
        default=None,
        description="Remaining scans available today (UTC), or null if unlimited",
    )
    reset_at: datetime = Field(
        description="ISO 8601 UTC timestamp when daily quota resets (00:00:00 UTC)",
    )
    effective_source: str = Field(
        description=(
            "Source of the effective policy: 'global_default' or 'user_override'"
        ),
    )


class ScanQuotaExceededDetail(BaseModel):
    """Error detail returned when a scan quota is exhausted or blocked."""

    code: str = Field(
        description=(
            "Machine-readable code: 'DAILY_SCAN_QUOTA_EXCEEDED' or 'SCAN_QUOTA_BLOCKED'"
        ),
    )
    message: str = Field(
        description="Human-readable explanation of the quota restriction",
    )
    quota: ScanQuotaInfo = Field(
        description="Quota metadata with the current limit, usage, and reset time",
    )


class UserScanQuotaOverrideRequest(BaseModel):
    """Payload to create or update a per-user scan quota override."""

    override_mode: Literal["inherit", "custom", "unlimited", "blocked"] = Field(
        ...,
        description="Quota override policy mode",
    )
    custom_limit: int | None = Field(
        default=None,
        description="Finite daily limit required when override_mode is 'custom'",
    )
    reason: str | None = Field(
        default=None,
        max_length=255,
        description="Administrative rationale for applying or updating this override",
    )

    @model_validator(mode="after")
    def validate_custom_limit(self) -> "UserScanQuotaOverrideRequest":
        if self.override_mode == "custom":
            if self.custom_limit is None or self.custom_limit < 0:
                raise ValueError(
                    "custom_limit must be non-negative when override_mode is 'custom'"
                )
        elif self.custom_limit is not None and self.override_mode != "custom":
            # Normalize custom_limit to None when mode is not custom
            self.custom_limit = None
        return self


class UserScanQuotaResponse(BaseModel):
    """Detailed user scan quota override and live daily consumption status."""

    model_config = ConfigDict(from_attributes=True)

    user_id: str = Field(description="UUID of user account")
    override_mode: str = Field(
        description="Policy mode: 'inherit', 'custom', 'unlimited', or 'blocked'",
    )
    custom_limit: int | None = Field(
        default=None,
        description="Custom finite limit if override_mode is 'custom'",
    )
    effective_limit: int | None = Field(
        default=None,
        description="Computed active limit (null if unlimited, 0 if blocked)",
    )
    used_today: int = Field(
        default=0,
        description="Scans accepted today in UTC",
    )
    remaining_today: int | None = Field(
        default=None,
        description="Scans remaining today in UTC (null if unlimited)",
    )
    reset_at: datetime = Field(
        description="UTC timestamp when quota window resets",
    )
    effective_source: str = Field(
        description=(
            "Effective configuration source: 'global_default' or 'user_override'"
        ),
    )
    reason: str | None = Field(
        default=None,
        description="Administrative note",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="Last update timestamp of user override",
    )


class ScanQuotaSettingsResponse(BaseModel):
    """Global scan quota settings response."""

    default_daily_limit: int = Field(
        description="System-wide default daily scans allowed per user",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="UTC timestamp when setting was last modified",
    )


class ScanQuotaSettingsUpdateRequest(BaseModel):
    """Payload to adjust the global default daily scan quota limit."""

    default_daily_limit: int = Field(
        ...,
        ge=0,
        description="New default daily scans allowed per user (>= 0)",
    )
