import concurrent.futures
import io
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.main import app
from app.models.scan import Scan
from app.models.user import User, UserSession
from app.services.auth import SESSION_COOKIE_NAME, hash_token
from app.services.scan_quota import QuotaExhaustedError, ScanQuotaService
from tests.conftest import TestingSessionLocal


def _make_jpeg_bytes(width: int = 120, height: int = 160) -> bytes:
    img = Image.new("RGB", (width, height), color=(50, 100, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _create_user(
    db: Session, email: str = "concurrency_user@example.com"
) -> tuple[User, str]:
    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash="test-pw-hash",
        role="user",
        is_active=True,
    )
    db.add(user)
    db.flush()

    token = f"concurrent-token-{uuid.uuid4().hex}"
    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        session_token_hash=hash_token(token),
        session_type="user",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    db.add(session)
    db.commit()
    return user, token


def test_concurrent_reserve_and_consume_exact_limit(db: Session):
    """Only the configured number of concurrent requests may succeed."""
    user, _ = _create_user(db, "racing_quota@example.com")
    user_id = str(user.id)
    quota_svc = ScanQuotaService(db)
    quota_svc.set_user_override(user_id, override_mode="custom", custom_limit=3)
    db.commit()

    num_threads = 10
    successes = []
    quota_exhausted_errors = []
    other_errors = []

    def _worker(thread_idx: int):
        thread_db = TestingSessionLocal()
        try:
            worker_svc = ScanQuotaService(thread_db)
            is_replay, info, existing_scan_id = worker_svc.reserve_and_consume_quota(
                user_id=user_id,
                anonymous_session_id=None,
                idempotency_key=f"worker-key-{thread_idx}",
            )
            successes.append((thread_idx, info.used))
        except QuotaExhaustedError as exc:
            quota_exhausted_errors.append((thread_idx, exc.code))
        except Exception as exc:
            other_errors.append((thread_idx, str(exc)))
        finally:
            thread_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(_worker, i) for i in range(num_threads)]
        concurrent.futures.wait(futures)

    assert len(other_errors) == 0, (
        f"Unexpected errors during concurrent test: {other_errors}"
    )
    assert len(successes) == 3, f"Expected exactly 3 successes, got {len(successes)}"
    assert len(quota_exhausted_errors) == 7, (
        f"Expected 7 exhausted errors, got {len(quota_exhausted_errors)}"
    )

    # Check database state
    verify_db = TestingSessionLocal()
    try:
        final_svc = ScanQuotaService(verify_db)
        status = final_svc.get_quota_status(user_id, None)
        assert status.used == 3
        assert status.remaining == 0
    finally:
        verify_db.close()


def test_concurrent_idempotent_replay_consumption(db: Session):
    """Concurrent requests sharing an idempotency key consume quota once."""
    user, _ = _create_user(db, "racing_idemp@example.com")
    user_id = str(user.id)
    quota_svc = ScanQuotaService(db)
    quota_svc.set_user_override(user_id, override_mode="custom", custom_limit=5)
    db.commit()

    same_key = f"shared-idemp-{uuid.uuid4().hex}"
    num_threads = 6
    results = []
    errors = []

    # First commit a scan with that key so replay is fully recognized
    init_db = TestingSessionLocal()
    try:
        scan_id = str(uuid.uuid4())
        scan = Scan(
            id=scan_id,
            user_id=user_id,
            status="uploaded",
            image_path=f"{scan_id}.jpg",
            content_type="image/jpeg",
            width=300,
            height=400,
            file_size=1234,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        init_db.add(scan)
        init_db.commit()

        init_svc = ScanQuotaService(init_db)
        is_replay, info, existing_id = init_svc.reserve_and_consume_quota(
            user_id=user_id,
            anonymous_session_id=None,
            idempotency_key=same_key,
        )
        assert not is_replay
        owner_key = init_svc.get_owner_key(user_id, None)
        init_svc.commit_scan_idempotency(owner_key, same_key, scan_id)
    finally:
        init_db.close()

    def _worker(thread_idx: int):
        thread_db = TestingSessionLocal()
        try:
            worker_svc = ScanQuotaService(thread_db)
            is_replay, info, existing_scan_id = worker_svc.reserve_and_consume_quota(
                user_id=user_id,
                anonymous_session_id=None,
                idempotency_key=same_key,
            )
            results.append((is_replay, existing_scan_id))
        except Exception as exc:
            errors.append((thread_idx, str(exc)))
        finally:
            thread_db.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(_worker, i) for i in range(num_threads)]
        concurrent.futures.wait(futures)

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    assert len(results) == num_threads
    for is_replay, returned_scan_id in results:
        assert is_replay is True
        assert returned_scan_id == scan_id

    # Total quota used must still be exactly 1
    verify_db = TestingSessionLocal()
    try:
        final_svc = ScanQuotaService(verify_db)
        status = final_svc.get_quota_status(user_id, None)
        assert status.used == 1
        assert status.remaining == 4
    finally:
        verify_db.close()


def test_concurrent_api_scan_uploads_quota_exhaustion():
    """Concurrent uploads stop atomically at the quota limit."""
    setup_db = TestingSessionLocal()
    try:
        user, token = _create_user(setup_db, "api_concurrency@example.com")
        user_id = user.id
        quota_svc = ScanQuotaService(setup_db)
        quota_svc.set_user_override(user_id, override_mode="custom", custom_limit=2)
    finally:
        setup_db.close()

    # Per-request DB sessions so threads don't share a session
    def _concurrent_get_db():
        thread_session = TestingSessionLocal()
        try:
            yield thread_session
        finally:
            thread_session.close()

    app.dependency_overrides[get_db] = _concurrent_get_db

    jpeg_data = _make_jpeg_bytes()
    num_requests = 6
    status_codes = []

    def _upload_worker(idx: int):
        client = TestClient(app)
        client.cookies.set(SESSION_COOKIE_NAME, token)
        res = client.post(
            "/api/v1/scans",
            files={"file": ("test.jpg", io.BytesIO(jpeg_data), "image/jpeg")},
            headers={"Idempotency-Key": f"api-concurrency-key-{idx:04d}"},
        )
        status_codes.append(res.status_code)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_requests) as executor:
        futures = [executor.submit(_upload_worker, i) for i in range(num_requests)]
        concurrent.futures.wait(futures)

    app.dependency_overrides.pop(get_db, None)

    created_count = status_codes.count(201)
    exhausted_count = status_codes.count(429)

    assert created_count == 2, (
        f"Expected 2 created scans, got {created_count} (statuses: {status_codes})"
    )
    assert exhausted_count == 4, (
        "Expected 4 exhausted requests, got "
        f"{exhausted_count} (statuses: {status_codes})"
    )

    # Verify usage in DB is 2
    verify_db = TestingSessionLocal()
    try:
        final_svc = ScanQuotaService(verify_db)
        status = final_svc.get_quota_status(user_id, None)
        assert status.used == 2
        assert status.remaining == 0
    finally:
        verify_db.close()
