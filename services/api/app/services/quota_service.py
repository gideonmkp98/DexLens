"""Quota service interface and domain protocol.

Integration Contract for Integration Agent:
The administration subsystem consumes the `QuotaServiceInterface` protocol.
When integrating the parallel `quota` branch, wire the concrete `QuotaService`
implementation to `get_quota_service` via FastAPI dependency injection or
container setup.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class GlobalQuotaSettings:
    """Read model for global system scan limits."""

    daily_scan_limit: int
    hourly_scan_limit: int
    updated_at: datetime | None = None


@dataclass
class UserQuotaOverview:
    """Read model for per-user effective scan limits and overrides."""

    user_id: str
    email: str
    effective_daily_limit: int
    custom_override: int | None
    reason: str | None
    scans_used_today: int
    remaining_today: int


class QuotaServiceInterface(Protocol):
    """Stable interface contract consumed by Admin and Scan subsystems for quotas."""

    def get_global_quota(self) -> GlobalQuotaSettings:
        """Fetch active system-wide scan quota configuration."""
        ...

    def update_global_quota(
        self,
        daily_limit: int,
        hourly_limit: int,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> GlobalQuotaSettings:
        """Update system-wide default scan quotas."""
        ...

    def get_user_quota(self, user_id: str) -> UserQuotaOverview:
        """Fetch effective scan quota and daily usage for a given user."""
        ...

    def set_user_quota_override(
        self,
        user_id: str,
        custom_limit: int | None,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> UserQuotaOverview:
        """Configure or clear custom scan quota override for a specific user."""
        ...
