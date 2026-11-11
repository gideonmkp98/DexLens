import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scan import Scan
from app.models.scan_quota import (
    DailyScanUsage,
    ScanIdempotencyRecord,
    ScanQuotaSetting,
    UserScanQuota,
)
from app.schemas.scan_quota import ScanQuotaInfo

logger = logging.getLogger(__name__)

GLOBAL_SETTING_DAILY_LIMIT_KEY = "default_daily_limit"


class QuotaExhaustedError(Exception):
    """Raised when an operation would exceed the user's daily scan quota."""

    def __init__(
        self,
        message: str,
        quota: ScanQuotaInfo,
        code: str = "DAILY_SCAN_QUOTA_EXCEEDED",
        status_code: int = 429,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.quota = quota
        self.code = code
        self.status_code = status_code


class ScanQuotaService:
    """Manage scan limits, metering, overrides, and idempotency."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # --------------------------------------------------------------------------
    # Utility methods
    # --------------------------------------------------------------------------

    @staticmethod
    def get_owner_key(user_id: str | None, anonymous_session_id: str | None) -> str:
        """Derive an explicit partition owner key."""
        if user_id:
            return f"user:{user_id}"
        if anonymous_session_id:
            return f"anon:{anonymous_session_id}"
        raise ValueError("Either user_id or anonymous_session_id must be provided.")

    @staticmethod
    def get_utc_date(at_time: datetime | None = None) -> date:
        """Return the UTC date for quota calculation."""
        if at_time is not None:
            if at_time.tzinfo is None:
                return at_time.date()
            return at_time.astimezone(UTC).date()
        return datetime.now(UTC).date()

    @staticmethod
    def get_next_reset_time(at_time: datetime | None = None) -> datetime:
        """Return next midnight (00:00:00) UTC timestamp."""
        current_date = ScanQuotaService.get_utc_date(at_time)
        return datetime(
            current_date.year,
            current_date.month,
            current_date.day,
            0,
            0,
            0,
            tzinfo=UTC,
        ) + timedelta(days=1)

    # --------------------------------------------------------------------------
    # Global settings
    # --------------------------------------------------------------------------

    def get_global_default_limit(self) -> int:
        """Retrieve system-wide default daily scan limit from DB or configuration."""
        setting = (
            self.db.query(ScanQuotaSetting)
            .filter(ScanQuotaSetting.key == GLOBAL_SETTING_DAILY_LIMIT_KEY)
            .first()
        )
        if setting and setting.value.isdigit():
            return int(setting.value)
        return settings.DEFAULT_DAILY_SCAN_LIMIT

    def get_global_settings_record(self) -> tuple[int, datetime | None]:
        """Retrieve system-wide default limit and last update timestamp."""
        setting = (
            self.db.query(ScanQuotaSetting)
            .filter(ScanQuotaSetting.key == GLOBAL_SETTING_DAILY_LIMIT_KEY)
            .first()
        )
        if setting:
            val = (
                int(setting.value)
                if setting.value.isdigit()
                else settings.DEFAULT_DAILY_SCAN_LIMIT
            )
            return val, setting.updated_at.replace(tzinfo=UTC)
        return settings.DEFAULT_DAILY_SCAN_LIMIT, None

    def set_global_default_limit(self, limit: int) -> tuple[int, datetime]:
        """Update system-wide default daily scan limit."""
        if limit < 0:
            raise ValueError("Default daily scan limit must be non-negative.")

        now_utc = datetime.now(UTC).replace(tzinfo=None)
        setting = (
            self.db.query(ScanQuotaSetting)
            .filter(ScanQuotaSetting.key == GLOBAL_SETTING_DAILY_LIMIT_KEY)
            .first()
        )
        if setting is None:
            setting = ScanQuotaSetting(
                key=GLOBAL_SETTING_DAILY_LIMIT_KEY,
                value=str(limit),
                description="Global default daily scans allowed per user",
                updated_at=now_utc,
            )
            self.db.add(setting)
        else:
            setting.value = str(limit)
            setting.updated_at = now_utc

        self.db.commit()
        self.db.refresh(setting)
        return limit, setting.updated_at.replace(tzinfo=UTC)

    # --------------------------------------------------------------------------
    # User overrides
    # --------------------------------------------------------------------------

    def get_user_override(self, user_id: str) -> UserScanQuota | None:
        """Retrieve user override record if present."""
        return (
            self.db.query(UserScanQuota)
            .filter(UserScanQuota.user_id == user_id)
            .first()
        )

    def set_user_override(
        self,
        user_id: str,
        override_mode: str,
        custom_limit: int | None = None,
        reason: str | None = None,
    ) -> UserScanQuota:
        """Set or update quota override for a specific user."""
        valid_modes = {"inherit", "custom", "unlimited", "blocked"}
        if override_mode not in valid_modes:
            raise ValueError(
                f"Invalid override_mode '{override_mode}'. Must be one of {valid_modes}"
            )

        if override_mode == "custom":
            if custom_limit is None or custom_limit < 0:
                raise ValueError(
                    "custom_limit must be non-negative when override_mode is 'custom'"
                )
        else:
            custom_limit = None

        now_utc = datetime.now(UTC).replace(tzinfo=None)
        override = self.get_user_override(user_id)
        if override is None:
            override = UserScanQuota(
                user_id=user_id,
                override_mode=override_mode,
                custom_limit=custom_limit,
                reason=reason,
                created_at=now_utc,
                updated_at=now_utc,
            )
            self.db.add(override)
        else:
            override.override_mode = override_mode
            override.custom_limit = custom_limit
            override.reason = reason
            override.updated_at = now_utc

        self.db.commit()
        self.db.refresh(override)
        return override

    def delete_user_override(self, user_id: str) -> bool:
        """Remove user quota override, reverting to global default."""
        override = self.get_user_override(user_id)
        if override:
            self.db.delete(override)
            self.db.commit()
            return True
        return False

    # --------------------------------------------------------------------------
    # Effective Quota & Status
    # --------------------------------------------------------------------------

    def resolve_effective_policy(
        self,
        user_id: str | None,
    ) -> tuple[int | None, str, str]:
        """Resolve (effective_limit, mode, effective_source) for the given user.

        - effective_limit: None if unlimited, 0 if blocked, or integer >= 0.
        - mode: 'inherit' | 'custom' | 'unlimited' | 'blocked'
        - effective_source: 'global_default' | 'user_override'
        """
        if user_id:
            override = self.get_user_override(user_id)
            if override:
                if override.override_mode == "blocked":
                    return 0, "blocked", "user_override"
                if override.override_mode == "unlimited":
                    return None, "unlimited", "user_override"
                if override.override_mode == "custom":
                    return override.custom_limit, "custom", "user_override"
                # "inherit"
                return self.get_global_default_limit(), "inherit", "global_default"

        return self.get_global_default_limit(), "inherit", "global_default"

    def get_used_count(self, owner_key: str, usage_date: date) -> int:
        """Fetch current used scans for given owner and date without locking."""
        row = (
            self.db.query(DailyScanUsage)
            .filter(
                DailyScanUsage.owner_key == owner_key,
                DailyScanUsage.usage_date == usage_date,
            )
            .first()
        )
        return row.used_count if row else 0

    def get_quota_status(
        self,
        user_id: str | None,
        anonymous_session_id: str | None,
        at_time: datetime | None = None,
    ) -> ScanQuotaInfo:
        """Compute structured quota metadata for given user or anonymous session."""
        owner_key = self.get_owner_key(user_id, anonymous_session_id)
        current_date = self.get_utc_date(at_time)
        reset_at = self.get_next_reset_time(at_time)

        effective_limit, mode, effective_source = self.resolve_effective_policy(user_id)
        used = self.get_used_count(owner_key, current_date)

        if mode == "blocked":
            remaining = 0
        elif effective_limit is None:  # unlimited
            remaining = None
        else:
            remaining = max(0, effective_limit - used)

        return ScanQuotaInfo(
            limit=effective_limit,
            used=used,
            remaining=remaining,
            reset_at=reset_at,
            effective_source=effective_source,
        )

    # --------------------------------------------------------------------------
    # Idempotency & Replay Lookup
    # --------------------------------------------------------------------------

    def find_idempotent_scan(
        self,
        owner_key: str,
        idempotency_key: str,
    ) -> Scan | None:
        """Look up existing completed scan for idempotent requests."""
        record = (
            self.db.query(ScanIdempotencyRecord)
            .filter(
                ScanIdempotencyRecord.owner_key == owner_key,
                ScanIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .first()
        )
        if record and record.scan_id:
            return self.db.query(Scan).filter(Scan.id == record.scan_id).first()
        return None

    # --------------------------------------------------------------------------
    # Atomic Quota Consumption
    # --------------------------------------------------------------------------

    def reserve_and_consume_quota(
        self,
        user_id: str | None,
        anonymous_session_id: str | None,
        idempotency_key: str | None = None,
        at_time: datetime | None = None,
    ) -> tuple[bool, ScanQuotaInfo, str | None]:
        """Atomically check and consume 1 daily scan quota unit.

        Returns:
            tuple of (is_replay, quota_info, existing_scan_id)
            - is_replay: True if request was an idempotent replay of an existing scan
            - quota_info: Structured quota metadata after consumption
            - existing_scan_id: ID of previously completed scan if is_replay is True

        Raises:
            QuotaExhaustedError: if quota is exhausted or account is blocked.
        """
        owner_key = self.get_owner_key(user_id, anonymous_session_id)
        current_date = self.get_utc_date(at_time)
        reset_at = self.get_next_reset_time(at_time)

        # 1. Check for durable idempotent replay first
        if idempotency_key:
            existing_record = (
                self.db.query(ScanIdempotencyRecord)
                .filter(
                    ScanIdempotencyRecord.owner_key == owner_key,
                    ScanIdempotencyRecord.idempotency_key == idempotency_key,
                )
                .first()
            )
            if existing_record is not None and existing_record.scan_id is not None:
                # Existing scan completed: return without consuming additional quota
                quota_status = self.get_quota_status(
                    user_id, anonymous_session_id, at_time
                )
                return True, quota_status, existing_record.scan_id

        # 2. Check effective policy
        effective_limit, mode, effective_source = self.resolve_effective_policy(user_id)
        if mode == "blocked":
            used = self.get_used_count(owner_key, current_date)
            status = ScanQuotaInfo(
                limit=0,
                used=used,
                remaining=0,
                reset_at=reset_at,
                effective_source=effective_source,
            )
            raise QuotaExhaustedError(
                message="Daily scan quota blocked for this account.",
                quota=status,
                code="SCAN_QUOTA_BLOCKED",
                status_code=429,
            )

        now_utc = datetime.now(UTC).replace(tzinfo=None)

        # 3. Ensure a row exists in daily_scan_usage for (owner_key, current_date)
        # Using database engine dialect check for portable testing (SQLite vs MariaDB)
        dialect_name = self.db.bind.dialect.name if self.db.bind else "mysql"

        if dialect_name in ("mysql", "mariadb"):
            # Use ON DUPLICATE KEY UPDATE to atomically ensure row existence
            ensure_sql = text(
                """
                INSERT INTO daily_scan_usage
                    (id, owner_key, user_id, anonymous_session_id,
                     usage_date, used_count, created_at, updated_at)
                VALUES
                    (:id, :owner_key, :user_id, :anon_id,
                     :usage_date, 0, :created_at, :updated_at)
                ON DUPLICATE KEY UPDATE updated_at = updated_at
                """
            )
            self.db.execute(
                ensure_sql,
                {
                    "id": str(uuid.uuid4()),
                    "owner_key": owner_key,
                    "user_id": user_id,
                    "anon_id": anonymous_session_id if not user_id else None,
                    "usage_date": current_date,
                    "created_at": now_utc,
                    "updated_at": now_utc,
                },
            )
        else:
            # SQLite fallback for in-memory unit tests
            existing = (
                self.db.query(DailyScanUsage)
                .filter(
                    DailyScanUsage.owner_key == owner_key,
                    DailyScanUsage.usage_date == current_date,
                )
                .first()
            )
            if not existing:
                try:
                    new_usage = DailyScanUsage(
                        id=str(uuid.uuid4()),
                        owner_key=owner_key,
                        user_id=user_id,
                        anonymous_session_id=anonymous_session_id
                        if not user_id
                        else None,
                        usage_date=current_date,
                        used_count=0,
                        created_at=now_utc,
                        updated_at=now_utc,
                    )
                    self.db.add(new_usage)
                    self.db.flush()
                except IntegrityError:
                    self.db.rollback()

        # 4. Lock the usage row for this owner and UTC date.
        usage_row = (
            self.db.query(DailyScanUsage)
            .filter(
                DailyScanUsage.owner_key == owner_key,
                DailyScanUsage.usage_date == current_date,
            )
            .with_for_update()
            .first()
        )

        if usage_row is None:
            # Defensive fallback
            usage_row = DailyScanUsage(
                id=str(uuid.uuid4()),
                owner_key=owner_key,
                user_id=user_id,
                anonymous_session_id=anonymous_session_id if not user_id else None,
                usage_date=current_date,
                used_count=0,
                created_at=now_utc,
                updated_at=now_utc,
            )
            self.db.add(usage_row)
            self.db.flush()

        # 5. Check finite limit against current usage under row lock
        if effective_limit is not None and usage_row.used_count >= effective_limit:
            status = ScanQuotaInfo(
                limit=effective_limit,
                used=usage_row.used_count,
                remaining=0,
                reset_at=reset_at,
                effective_source=effective_source,
            )
            self.db.rollback()
            raise QuotaExhaustedError(
                message="Daily scan quota exceeded. Please try again tomorrow.",
                quota=status,
                code="DAILY_SCAN_QUOTA_EXCEEDED",
                status_code=429,
            )

        # 6. Increment consumption counter
        usage_row.used_count += 1
        usage_row.updated_at = now_utc

        # 7. Record idempotency reservation if key was provided
        if idempotency_key:
            idemp_record = (
                self.db.query(ScanIdempotencyRecord)
                .filter(
                    ScanIdempotencyRecord.owner_key == owner_key,
                    ScanIdempotencyRecord.idempotency_key == idempotency_key,
                )
                .first()
            )
            if idemp_record is None:
                idemp_record = ScanIdempotencyRecord(
                    id=str(uuid.uuid4()),
                    owner_key=owner_key,
                    idempotency_key=idempotency_key,
                    scan_id=None,
                    usage_date=current_date,
                    created_at=now_utc,
                )
                self.db.add(idemp_record)

        self.db.commit()

        new_used = usage_row.used_count
        new_remaining = (
            max(0, effective_limit - new_used) if effective_limit is not None else None
        )

        quota_status = ScanQuotaInfo(
            limit=effective_limit,
            used=new_used,
            remaining=new_remaining,
            reset_at=reset_at,
            effective_source=effective_source,
        )
        return False, quota_status, None

    def commit_scan_idempotency(
        self,
        owner_key: str,
        idempotency_key: str | None,
        scan_id: str,
    ) -> None:
        """Bind created scan_id to the idempotency record."""
        if not idempotency_key:
            return
        record = (
            self.db.query(ScanIdempotencyRecord)
            .filter(
                ScanIdempotencyRecord.owner_key == owner_key,
                ScanIdempotencyRecord.idempotency_key == idempotency_key,
            )
            .first()
        )
        if record:
            record.scan_id = scan_id
            self.db.commit()

    def rollback_consumption(
        self,
        owner_key: str,
        usage_date: date,
        idempotency_key: str | None = None,
    ) -> None:
        """Revert a quota increment if scan creation/storage unexpectedly failed."""
        try:
            usage_row = (
                self.db.query(DailyScanUsage)
                .filter(
                    DailyScanUsage.owner_key == owner_key,
                    DailyScanUsage.usage_date == usage_date,
                )
                .with_for_update()
                .first()
            )
            if usage_row and usage_row.used_count > 0:
                usage_row.used_count -= 1
                usage_row.updated_at = datetime.now(UTC).replace(tzinfo=None)

            if idempotency_key:
                record = (
                    self.db.query(ScanIdempotencyRecord)
                    .filter(
                        ScanIdempotencyRecord.owner_key == owner_key,
                        ScanIdempotencyRecord.idempotency_key == idempotency_key,
                    )
                    .first()
                )
                if record and record.scan_id is None:
                    self.db.delete(record)

            self.db.commit()
        except Exception as exc:
            logger.warning("Failed to rollback quota consumption: %s", exc)
            self.db.rollback()


def get_scan_quota_service(db: Session) -> ScanQuotaService:
    return ScanQuotaService(db)
