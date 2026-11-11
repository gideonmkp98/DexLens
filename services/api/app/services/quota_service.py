import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class GlobalQuotaSettings:
    daily_scan_limit: int
    hourly_scan_limit: int
    updated_at: datetime | None = None


@dataclass
class UserQuotaOverview:
    user_id: str
    email: str
    effective_daily_limit: int
    custom_override: int | None
    reason: str | None
    scans_used_today: int
    remaining_today: int


class QuotaServiceInterface(Protocol):
    """Interface contract consumed by Admin and Scan subsystems for quotas."""

    def get_global_quota(self) -> GlobalQuotaSettings: ...

    def update_global_quota(
        self,
        daily_limit: int,
        hourly_limit: int,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> GlobalQuotaSettings: ...

    def get_user_quota(self, user_id: str) -> UserQuotaOverview: ...

    def set_user_quota_override(
        self,
        user_id: str,
        custom_limit: int | None,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> UserQuotaOverview: ...


class DefaultQuotaService:
    """Production implementation interfacing with Quota domain or fallback."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._table_names: set[str] | None = None

    def _get_table_names(self) -> set[str]:
        if self._table_names is None:
            insp = inspect(self.db.bind)
            self._table_names = set(insp.get_table_names())
        return self._table_names

    def get_global_quota(self) -> GlobalQuotaSettings:
        tables = self._get_table_names()
        daily = settings.GLOBAL_DEFAULT_DAILY_SCAN_QUOTA
        hourly = settings.GLOBAL_DEFAULT_HOURLY_SCAN_QUOTA
        updated_at = None

        if "scan_quota_settings" in tables:
            rows = self.db.execute(
                text("SELECT `key`, `value`, `updated_at` FROM scan_quota_settings")
            ).fetchall()
            for key, val, upd in rows:
                try:
                    if key == "daily_scan_limit":
                        daily = int(val)
                        updated_at = upd
                    elif key == "hourly_scan_limit":
                        hourly = int(val)
                        if not updated_at:
                            updated_at = upd
                except (ValueError, TypeError):
                    pass

        return GlobalQuotaSettings(
            daily_scan_limit=daily,
            hourly_scan_limit=hourly,
            updated_at=updated_at,
        )

    def update_global_quota(
        self,
        daily_limit: int,
        hourly_limit: int,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> GlobalQuotaSettings:
        tables = self._get_table_names()
        now = _utcnow()

        if "scan_quota_settings" in tables:
            for key, val, desc in (
                ("daily_scan_limit", str(daily_limit), "Max scans per day"),
                ("hourly_scan_limit", str(hourly_limit), "Max scans per hour"),
            ):
                self.db.execute(
                    text(
                        """
                        INSERT INTO scan_quota_settings (`key`, `value`, `description`, `updated_at`)
                        VALUES (:k, :v, :d, :u)
                        ON DUPLICATE KEY UPDATE `value` = :v, `updated_at` = :u
                        """
                    ),
                    {"k": key, "v": val, "d": desc, "u": now},
                )
            self.db.commit()

        # Update runtime settings
        settings.GLOBAL_DEFAULT_DAILY_SCAN_QUOTA = daily_limit
        settings.GLOBAL_DEFAULT_HOURLY_SCAN_QUOTA = hourly_limit

        return GlobalQuotaSettings(
            daily_scan_limit=daily_limit,
            hourly_scan_limit=hourly_limit,
            updated_at=now,
        )

    def get_user_quota(self, user_id: str) -> UserQuotaOverview:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        global_quota = self.get_global_quota()
        custom_override = user.scan_quota_override
        reason = None

        tables = self._get_table_names()
        if "user_scan_quotas" in tables:
            row = self.db.execute(
                text(
                    "SELECT custom_limit, reason FROM user_scan_quotas WHERE user_id = :uid"
                ),
                {"uid": user_id},
            ).first()
            if row:
                custom_override = row[0]
                reason = row[1]

        effective_limit = (
            custom_override
            if custom_override is not None
            else global_quota.daily_scan_limit
        )

        # Scans used today
        scans_today = 0
        if "daily_scan_usage" in tables:
            today_str = _utcnow().strftime("%Y-%m-%d")
            row_usage = self.db.execute(
                text(
                    "SELECT used_count FROM daily_scan_usage WHERE user_id = :uid AND usage_date = :dt"
                ),
                {"uid": user_id, "dt": today_str},
            ).first()
            if row_usage:
                scans_today = row_usage[0]
        else:
            # Fallback counting today's scans from scans table
            from app.models.scan import Scan

            today_start = _utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            scans_today = (
                self.db.query(Scan)
                .filter(Scan.user_id == user_id, Scan.created_at >= today_start)
                .count()
            )

        remaining = max(0, effective_limit - scans_today)

        return UserQuotaOverview(
            user_id=user.id,
            email=user.email,
            effective_daily_limit=effective_limit,
            custom_override=custom_override,
            reason=reason,
            scans_used_today=scans_today,
            remaining_today=remaining,
        )

    def set_user_quota_override(
        self,
        user_id: str,
        custom_limit: int | None,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> UserQuotaOverview:
        user = self.db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError(f"User {user_id} not found")

        user.scan_quota_override = custom_limit
        self.db.add(user)

        tables = self._get_table_names()
        now = _utcnow()
        if "user_scan_quotas" in tables:
            if custom_limit is not None:
                self.db.execute(
                    text(
                        """
                        INSERT INTO user_scan_quotas (user_id, override_mode, custom_limit, reason, created_at, updated_at)
                        VALUES (:uid, 'custom', :lim, :r, :now, :now)
                        ON DUPLICATE KEY UPDATE override_mode = 'custom', custom_limit = :lim, reason = :r, updated_at = :now
                        """
                    ),
                    {"uid": user_id, "lim": custom_limit, "r": reason, "now": now},
                )
            else:
                self.db.execute(
                    text("DELETE FROM user_scan_quotas WHERE user_id = :uid"),
                    {"uid": user_id},
                )

        self.db.commit()
        return self.get_user_quota(user_id)
