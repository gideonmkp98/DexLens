import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import User, UserSession
from app.services.auth import SESSION_COOKIE_NAME, hash_token
from app.services.scan_quota import ScanQuotaService


def _make_jpeg_bytes(width: int = 300, height: int = 420) -> bytes:
    img = Image.new("RGB", (width, height), color=(60, 120, 180))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _create_authenticated_client(db: Session, email: str, role: str = "user") -> tuple[TestClient, User]:
    from app.main import app

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        password_hash="fake-hash",
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()

    token = f"test-token-{uuid.uuid4().hex}"
    session = UserSession(
        id=str(uuid.uuid4()),
        user_id=user.id,
        session_token_hash=hash_token(token),
        session_type="user",
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
    )
    db.add(session)
    db.commit()

    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE_NAME, token)
    return client, user


def test_get_scan_quota_anonymous(client: TestClient):
    res = client.get("/api/v1/scans/quota")
    assert res.status_code == 200
    data = res.json()

    assert data["limit"] == settings.DEFAULT_DAILY_SCAN_LIMIT
    assert data["used"] == 0
    assert data["remaining"] == settings.DEFAULT_DAILY_SCAN_LIMIT
    assert "reset_at" in data
    assert data["effective_source"] == "global_default"

    assert res.headers.get("X-Quota-Limit") == str(settings.DEFAULT_DAILY_SCAN_LIMIT)
    assert res.headers.get("X-Quota-Used") == "0"
    assert res.headers.get("X-Quota-Remaining") == str(settings.DEFAULT_DAILY_SCAN_LIMIT)
    assert res.headers.get("X-Quota-Source") == "global_default"


def test_upload_scan_consumes_quota_and_headers(client: TestClient, db: Session):
    quota_before = client.get("/api/v1/scans/quota").json()
    assert quota_before["used"] == 0

    image_bytes = _make_jpeg_bytes()
    files = {"file": ("test_card.jpg", image_bytes, "image/jpeg")}
    res = client.post("/api/v1/scans", files=files)
    assert res.status_code == 201
    data = res.json()

    # Quota in JSON response
    assert "quota" in data
    assert data["quota"]["used"] == 1
    assert data["quota"]["remaining"] == quota_before["limit"] - 1

    # Quota in Response headers
    assert res.headers.get("X-Quota-Used") == "1"
    assert res.headers.get("X-Quota-Remaining") == str(quota_before["limit"] - 1)

    # Polling GET /scans/{id} does not consume quota
    scan_id = data["id"]
    get_res = client.get(f"/api/v1/scans/{scan_id}")
    assert get_res.status_code == 200

    quota_after = client.get("/api/v1/scans/quota").json()
    assert quota_after["used"] == 1


def test_validation_failure_does_not_consume_quota(client: TestClient):
    quota_before = client.get("/api/v1/scans/quota").json()

    # 1. Invalid empty file
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    res = client.post("/api/v1/scans", files=files)
    assert res.status_code in (400, 422)

    # 2. Invalid non-image content
    files = {"file": ("bad.jpg", b"not-an-image-content-here", "image/jpeg")}
    res2 = client.post("/api/v1/scans", files=files)
    assert res2.status_code in (400, 415, 422)

    # Quota used remains strictly 0
    quota_after = client.get("/api/v1/scans/quota").json()
    assert quota_after["used"] == quota_before["used"]


def test_idempotent_replay_upload(client: TestClient):
    image_bytes = _make_jpeg_bytes()
    headers = {"Idempotency-Key": "idemp-upload-key-001"}

    # First attempt
    res1 = client.post(
        "/api/v1/scans",
        files={"file": ("card.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert res1.status_code == 201
    scan1 = res1.json()
    assert res1.headers.get("X-Quota-Used") == "1"

    # Replay identical request
    res2 = client.post(
        "/api/v1/scans",
        files={"file": ("card.jpg", image_bytes, "image/jpeg")},
        headers=headers,
    )
    assert res2.status_code in (200, 201)
    scan2 = res2.json()

    # Same scan returned, quota used is still 1
    assert scan2["id"] == scan1["id"]
    assert res2.headers.get("X-Quota-Used") == "1"

    quota = client.get("/api/v1/scans/quota").json()
    assert quota["used"] == 1


def test_live_capture_consumes_quota_and_idempotency(client: TestClient):
    # 1. Create session
    session_res = client.post("/api/v1/scan-sessions", json={})
    assert session_res.status_code == 201
    session_id = session_res.json()["id"]

    image_bytes = _make_jpeg_bytes()
    live_headers = {"Idempotency-Key": "live-capture-key-100"}

    # 2. Capture frame
    cap_res1 = client.post(
        f"/api/v1/scan-sessions/{session_id}/capture",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
        headers=live_headers,
    )
    assert cap_res1.status_code == 200
    cap_data1 = cap_res1.json()
    assert cap_data1["scan"]["quota"]["used"] == 1
    assert cap_res1.headers.get("X-Quota-Used") == "1"

    # 3. Idempotent replay of same live capture frame
    cap_res2 = client.post(
        f"/api/v1/scan-sessions/{session_id}/capture",
        files={"file": ("frame.jpg", image_bytes, "image/jpeg")},
        headers=live_headers,
    )
    assert cap_res2.status_code == 200
    cap_data2 = cap_res2.json()
    assert cap_data2["scan"]["id"] == cap_data1["scan"]["id"]
    assert cap_res2.headers.get("X-Quota-Used") == "1"

    # Overall quota used is 1
    quota = client.get("/api/v1/scans/quota").json()
    assert quota["used"] == 1


def test_quota_exhausted_structured_error_and_headers(db: Session):
    auth_client, user = _create_authenticated_client(db, "quota_exhaust_api@example.com")
    service = ScanQuotaService(db)
    # Set limit to 2 for this user
    service.set_user_override(user.id, "custom", custom_limit=2)

    image_bytes = _make_jpeg_bytes()

    # Upload 1
    r1 = auth_client.post("/api/v1/scans", files={"file": ("c1.jpg", image_bytes, "image/jpeg")})
    assert r1.status_code == 201
    assert r1.headers.get("X-Quota-Remaining") == "1"

    # Upload 2
    r2 = auth_client.post("/api/v1/scans", files={"file": ("c2.jpg", image_bytes, "image/jpeg")})
    assert r2.status_code == 201
    assert r2.headers.get("X-Quota-Remaining") == "0"

    # Upload 3 -> Quota exhausted
    r3 = auth_client.post("/api/v1/scans", files={"file": ("c3.jpg", image_bytes, "image/jpeg")})
    assert r3.status_code == 429
    err = r3.json()

    assert err["code"] == "DAILY_SCAN_QUOTA_EXCEEDED"
    assert "quota" in err
    assert err["quota"]["limit"] == 2
    assert err["quota"]["used"] == 2
    assert err["quota"]["remaining"] == 0
    assert err["quota"]["effective_source"] == "user_override"

    assert "Retry-After" in r3.headers
    assert r3.headers.get("X-Quota-Remaining") == "0"
    assert r3.headers.get("X-Quota-Used") == "2"


def test_blocked_user_api_error(db: Session):
    auth_client, user = _create_authenticated_client(db, "blocked_api@example.com")
    service = ScanQuotaService(db)
    service.set_user_override(user.id, "blocked")

    image_bytes = _make_jpeg_bytes()
    res = auth_client.post("/api/v1/scans", files={"file": ("blocked.jpg", image_bytes, "image/jpeg")})
    assert res.status_code == 429
    err = res.json()

    assert err["code"] == "SCAN_QUOTA_BLOCKED"
    assert err["quota"]["limit"] == 0
    assert err["quota"]["remaining"] == 0
    assert res.headers.get("X-Quota-Limit") == "0"


def test_unlimited_user_can_exceed_limits(db: Session):
    auth_client, user = _create_authenticated_client(db, "unlimited_api@example.com")
    service = ScanQuotaService(db)
    service.set_user_override(user.id, "unlimited")

    image_bytes = _make_jpeg_bytes()
    for i in range(1, 4):
        res = auth_client.post("/api/v1/scans", files={"file": (f"c{i}.jpg", image_bytes, "image/jpeg")})
        assert res.status_code == 201
        assert res.headers.get("X-Quota-Limit") == "unlimited"
        assert res.headers.get("X-Quota-Remaining") == "unlimited"
        assert res.headers.get("X-Quota-Used") == str(i)


def test_admin_scan_quota_authorization(db: Session, client: TestClient):
    auth_client, regular_user = _create_authenticated_client(db, "regular@example.com", role="user")

    # Anonymous -> 403 Forbidden
    res_anon = client.get("/api/v1/admin/scan-quota/settings")
    assert res_anon.status_code == 403

    # Regular user -> 403 Forbidden
    res_user = auth_client.get("/api/v1/admin/scan-quota/settings")
    assert res_user.status_code == 403

    # Pilot secret token header -> 200 OK
    res_pilot = client.get(
        "/api/v1/admin/scan-quota/settings",
        headers={"X-Pilot-Admin-Token": settings.PILOT_ADMIN_SECRET},
    )
    assert res_pilot.status_code == 200

    # Pilot user session -> 200 OK
    admin_client, _ = _create_authenticated_client(db, "admin@example.com", role="admin")
    res_admin = admin_client.get("/api/v1/admin/scan-quota/settings")
    assert res_admin.status_code == 200


def test_admin_scan_quota_crud_flow(db: Session):
    admin_client, _ = _create_authenticated_client(db, "admin_crud@example.com", role="admin")
    _, target_user = _create_authenticated_client(db, "target_user@example.com", role="user")

    # 1. Get global settings
    get_sett = admin_client.get("/api/v1/admin/scan-quota/settings")
    assert get_sett.status_code == 200
    assert "default_daily_limit" in get_sett.json()

    # 2. Update global settings
    put_sett = admin_client.put(
        "/api/v1/admin/scan-quota/settings",
        json={"default_daily_limit": 20},
    )
    assert put_sett.status_code == 200
    assert put_sett.json()["default_daily_limit"] == 20

    # 3. Get user quota
    get_user = admin_client.get(f"/api/v1/admin/scan-quota/users/{target_user.id}")
    assert get_user.status_code == 200
    assert get_user.json()["override_mode"] == "inherit"
    assert get_user.json()["effective_limit"] == 20

    # 4. Put user override
    put_user = admin_client.put(
        f"/api/v1/admin/scan-quota/users/{target_user.id}",
        json={"override_mode": "custom", "custom_limit": 100, "reason": "Power collector"},
    )
    assert put_user.status_code == 200
    assert put_user.json()["override_mode"] == "custom"
    assert put_user.json()["effective_limit"] == 100
    assert put_user.json()["reason"] == "Power collector"

    # 5. Delete user override (reverts to inherit)
    del_user = admin_client.delete(f"/api/v1/admin/scan-quota/users/{target_user.id}")
    assert del_user.status_code == 200
    assert del_user.json()["override_mode"] == "inherit"
    assert del_user.json()["effective_limit"] == 20
