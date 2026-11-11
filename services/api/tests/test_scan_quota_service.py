import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scan import Scan
from app.models.user import User
from app.services.scan_quota import (
    QuotaExhaustedError,
    ScanQuotaService,
)


def _create_test_user(db: Session, email: str = "quota_user@example.com") -> User:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash="fakehash",
        role="user",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_owner_key_resolution():
    uid = str(uuid.uuid4())
    anon_id = str(uuid.uuid4())

    assert ScanQuotaService.get_owner_key(uid, None) == f"user:{uid}"
    assert ScanQuotaService.get_owner_key(None, anon_id) == f"anon:{anon_id}"
    assert ScanQuotaService.get_owner_key(uid, anon_id) == f"user:{uid}"

    with pytest.raises(ValueError):
        ScanQuotaService.get_owner_key(None, None)


def test_utc_date_and_reset_time_calculation():
    # Morning in UTC
    t1 = datetime(2026, 11, 11, 8, 30, 0, tzinfo=UTC)
    assert ScanQuotaService.get_utc_date(t1) == date(2026, 11, 11)
    reset1 = ScanQuotaService.get_next_reset_time(t1)
    assert reset1 == datetime(2026, 11, 12, 0, 0, 0, tzinfo=UTC)

    # 1 second before midnight UTC
    t2 = datetime(2026, 11, 11, 23, 59, 59, tzinfo=UTC)
    assert ScanQuotaService.get_utc_date(t2) == date(2026, 11, 11)
    reset2 = ScanQuotaService.get_next_reset_time(t2)
    assert reset2 == datetime(2026, 11, 12, 0, 0, 0, tzinfo=UTC)

    # Midnight exactly (Day 2 starts)
    t3 = datetime(2026, 11, 12, 0, 0, 0, tzinfo=UTC)
    assert ScanQuotaService.get_utc_date(t3) == date(2026, 11, 12)
    reset3 = ScanQuotaService.get_next_reset_time(t3)
    assert reset3 == datetime(2026, 11, 13, 0, 0, 0, tzinfo=UTC)


def test_global_settings_and_dynamic_changes(db: Session):
    service = ScanQuotaService(db)

    # Default value before any DB record
    assert service.get_global_default_limit() == settings.DEFAULT_DAILY_SCAN_LIMIT

    # Dynamically update setting to 15
    limit, updated_at = service.set_global_default_limit(15)
    assert limit == 15
    assert updated_at is not None
    assert service.get_global_default_limit() == 15

    # Invalid negative limit
    with pytest.raises(ValueError):
        service.set_global_default_limit(-5)


def test_per_user_overrides_lifecycle(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "override_test@example.com")

    # Initially inherits global default
    effective_limit, mode, source = service.resolve_effective_policy(user.id)
    assert mode == "inherit"
    assert source == "global_default"
    assert effective_limit == service.get_global_default_limit()

    # Set custom finite limit
    service.set_user_override(
        user.id, "custom", custom_limit=25, reason="VIP beta tester"
    )
    effective_limit, mode, source = service.resolve_effective_policy(user.id)
    assert mode == "custom"
    assert source == "user_override"
    assert effective_limit == 25

    # Set unlimited
    service.set_user_override(user.id, "unlimited")
    effective_limit, mode, source = service.resolve_effective_policy(user.id)
    assert mode == "unlimited"
    assert source == "user_override"
    assert effective_limit is None

    # Set blocked
    service.set_user_override(user.id, "blocked", reason="Abusive activity")
    effective_limit, mode, source = service.resolve_effective_policy(user.id)
    assert mode == "blocked"
    assert source == "user_override"
    assert effective_limit == 0

    # Delete override -> reverts to inherit
    assert service.delete_user_override(user.id) is True
    effective_limit, mode, source = service.resolve_effective_policy(user.id)
    assert mode == "inherit"
    assert source == "global_default"
    assert effective_limit == service.get_global_default_limit()


def test_quota_consumption_and_exhaustion(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "consume_test@example.com")
    service.set_user_override(user.id, "custom", custom_limit=2)

    # Scan 1
    is_replay, quota1, _ = service.reserve_and_consume_quota(user.id, None)
    assert not is_replay
    assert quota1.limit == 2
    assert quota1.used == 1
    assert quota1.remaining == 1
    assert quota1.effective_source == "user_override"

    # Scan 2
    is_replay, quota2, _ = service.reserve_and_consume_quota(user.id, None)
    assert not is_replay
    assert quota2.used == 2
    assert quota2.remaining == 0

    # Scan 3 -> QuotaExhaustedError
    with pytest.raises(QuotaExhaustedError) as exc_info:
        service.reserve_and_consume_quota(user.id, None)

    assert exc_info.value.code == "DAILY_SCAN_QUOTA_EXCEEDED"
    assert exc_info.value.quota.used == 2
    assert exc_info.value.quota.remaining == 0


def test_blocked_user_consumption(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "blocked_user@example.com")
    service.set_user_override(user.id, "blocked")

    with pytest.raises(QuotaExhaustedError) as exc_info:
        service.reserve_and_consume_quota(user.id, None)

    assert exc_info.value.code == "SCAN_QUOTA_BLOCKED"
    assert exc_info.value.quota.limit == 0
    assert exc_info.value.quota.remaining == 0


def test_unlimited_user_consumption(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "unlimited_user@example.com")
    service.set_user_override(user.id, "unlimited")

    for i in range(1, 10):
        is_replay, quota, _ = service.reserve_and_consume_quota(user.id, None)
        assert not is_replay
        assert quota.limit is None
        assert quota.remaining is None
        assert quota.used == i


def test_idempotent_replay_does_not_consume_quota(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "idemp_test@example.com")
    service.set_user_override(user.id, "custom", custom_limit=3)

    idemp_key = "test-replay-key-12345"

    # 1. First request consumes 1
    is_replay1, quota1, _ = service.reserve_and_consume_quota(
        user.id, None, idempotency_key=idemp_key
    )
    assert not is_replay1
    assert quota1.used == 1

    # Simulate scan creation and binding
    fake_scan = Scan(
        id=str(uuid.uuid4()),
        user_id=user.id,
        status="uploaded",
        image_path="test.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=1000,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
    )
    db.add(fake_scan)
    db.commit()
    service.commit_scan_idempotency(f"user:{user.id}", idemp_key, fake_scan.id)

    # 2. Replayed request with same idempotency key
    is_replay2, quota2, existing_id = service.reserve_and_consume_quota(
        user.id, None, idempotency_key=idemp_key
    )
    assert is_replay2 is True
    assert existing_id == fake_scan.id
    assert quota2.used == 1  # Still 1! Not 2!


def test_boundary_day_rollover(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "boundary_test@example.com")
    service.set_user_override(user.id, "custom", custom_limit=1)

    day1_end = datetime(2026, 11, 11, 23, 59, 59, tzinfo=UTC)
    day2_start = datetime(2026, 11, 12, 0, 0, 1, tzinfo=UTC)

    # Day 1: consume quota (reaches limit)
    is_replay, q1, _ = service.reserve_and_consume_quota(
        user.id, None, at_time=day1_end
    )
    assert q1.used == 1
    assert q1.remaining == 0

    # Day 1: second attempt fails
    with pytest.raises(QuotaExhaustedError):
        service.reserve_and_consume_quota(user.id, None, at_time=day1_end)

    # Day 2: fresh quota window!
    is_replay2, q2, _ = service.reserve_and_consume_quota(
        user.id, None, at_time=day2_start
    )
    assert is_replay2 is False
    assert q2.used == 1
    assert q2.remaining == 0
    assert q2.reset_at == datetime(2026, 11, 13, 0, 0, 0, tzinfo=UTC)


def test_rollback_consumption(db: Session):
    service = ScanQuotaService(db)
    user = _create_test_user(db, "rollback_test@example.com")
    service.set_user_override(user.id, "custom", custom_limit=5)

    idemp_key = "test-rollback-key-99"
    _, q, _ = service.reserve_and_consume_quota(
        user.id, None, idempotency_key=idemp_key
    )
    assert q.used == 1

    # Roll back
    service.rollback_consumption(
        f"user:{user.id}", service.get_utc_date(), idempotency_key=idemp_key
    )

    # Usage is back to 0
    status = service.get_quota_status(user.id, None)
    assert status.used == 0
    assert status.remaining == 5
