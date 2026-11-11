import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.deps import (
    get_beta_service,
    get_optional_quota_service,
    get_quota_service,
)
from app.main import app
from app.models.user import User
from app.services.auth import (
    SESSION_COOKIE_NAME,
    AuthService,
)
from tests.fakes import FakeBetaService, FakeQuotaService


@pytest.fixture
def admin_client(db: Session) -> tuple[TestClient, User]:
    aclient = TestClient(app)
    auth = AuthService(db)
    admin = auth.register_user(
        f"admin_{uuid.uuid4().hex[:6]}@example.com",
        "AdminSecret123!",
        role="admin",
    )
    _, token = auth.create_session(user_id=admin.id, session_type="authenticated")
    aclient.cookies.set(SESSION_COOKIE_NAME, token)
    return aclient, admin


@pytest.fixture
def user_client(db: Session) -> tuple[TestClient, User]:
    uclient = TestClient(app)
    auth = AuthService(db)
    user = auth.register_user(
        f"user_{uuid.uuid4().hex[:6]}@example.com",
        "UserSecret123!",
        role="user",
    )
    _, token = auth.create_session(user_id=user.id, session_type="authenticated")
    uclient.cookies.set(SESSION_COOKIE_NAME, token)
    return uclient, user


def test_anonymous_admin_access_rejected(client: TestClient):
    client.cookies.clear()
    res = client.get("/api/v1/admin/users")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "UNAUTHENTICATED"


def test_regular_user_admin_access_rejected(user_client: tuple[TestClient, User]):
    uclient, _ = user_client
    res = uclient.get("/api/v1/admin/users")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "FORBIDDEN"


def test_client_supplied_role_spoofing_ignored(user_client: tuple[TestClient, User]):
    uclient, _ = user_client
    # Attempt to spoof role via header or request parameters
    res = uclient.get(
        "/api/v1/admin/users",
        headers={"X-User-Role": "admin", "Role": "admin"},
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "FORBIDDEN"


def test_admin_user_lookup_and_details(
    admin_client: tuple[TestClient, User],
    user_client: tuple[TestClient, User],
):
    aclient, admin = admin_client
    _, user = user_client

    # List users
    res = aclient.get("/api/v1/admin/users")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 2
    items = data["items"]

    # Verify no password hashes or raw secrets exposed
    for item in items:
        assert "password_hash" not in item
        assert "password" not in item
        assert "raw_token" not in item
        assert item["status"] in ("active", "suspended", "blocked")
        assert item["verification_status"] in (
            "verified",
            "unverified",
            "pending",
        )

    # Filter by search
    res_filter = aclient.get(f"/api/v1/admin/users?q={user.email}")
    assert res_filter.status_code == 200
    assert res_filter.json()["total"] == 1
    assert res_filter.json()["items"][0]["id"] == user.id

    # Get user details
    res_details = aclient.get(f"/api/v1/admin/users/{user.id}")
    assert res_details.status_code == 200
    details = res_details.json()
    assert details["email"] == user.email
    assert "quota" in details
    assert "scans_count" in details
    assert "recent_audit_events" in details


def test_admin_user_status_transition_and_session_killing(
    admin_client: tuple[TestClient, User],
    user_client: tuple[TestClient, User],
    db: Session,
):
    aclient, admin = admin_client
    uclient, user = user_client

    # Verify regular user session works
    res_me = uclient.get("/api/v1/auth/me")
    assert res_me.status_code == 200
    assert res_me.json()["is_authenticated"] is True

    # Admin suspends user
    res_suspend = aclient.patch(
        f"/api/v1/admin/users/{user.id}/status",
        json={"status": "suspended", "reason": "Terms of service violation"},
    )
    assert res_suspend.status_code == 200
    assert res_suspend.json()["status"] == "suspended"
    assert res_suspend.json()["is_active"] is False

    # User's active session must be killed/invalidated
    res_me_after = uclient.get("/api/v1/auth/me")
    assert res_me_after.json()["is_authenticated"] is False

    # Check audit log recorded this action
    res_audit = aclient.get(f"/api/v1/admin/audit-logs?target_id={user.id}")
    assert res_audit.status_code == 200
    logs = res_audit.json()["items"]
    assert len(logs) >= 1
    assert logs[0]["action"] == "user.suspended"
    assert logs[0]["actor_id"] == admin.id
    metadata = json.loads(logs[0]["metadata_json"])
    assert metadata["reason"] == "Terms of service violation"


def test_admin_cannot_suspend_self(admin_client: tuple[TestClient, User]):
    aclient, admin = admin_client
    res = aclient.patch(
        f"/api/v1/admin/users/{admin.id}/status",
        json={"status": "suspended", "reason": "Testing self-lockout guard"},
    )
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "CANNOT_MODIFY_SELF"


def test_unconfigured_quota_and_beta_returns_503(
    admin_client: tuple[TestClient, User],
    user_client: tuple[TestClient, User],
):
    """Unconfigured beta and quota services return 503."""
    aclient, _ = admin_client
    _, user = user_client

    # Global quota returns 503
    res_gquota = aclient.get("/api/v1/admin/settings/quota")
    assert res_gquota.status_code == 503
    assert res_gquota.json()["detail"]["code"] == "FEATURE_NOT_CONFIGURED"

    # User quota override returns 503
    res_uquota = aclient.patch(
        f"/api/v1/admin/users/{user.id}/quota",
        json={"scan_quota_override": 250, "reason": "Unconfigured test"},
    )
    assert res_uquota.status_code == 503
    assert res_uquota.json()["detail"]["code"] == "FEATURE_NOT_CONFIGURED"

    # Beta code list returns 503
    res_beta = aclient.get("/api/v1/admin/beta/codes")
    assert res_beta.status_code == 503
    assert res_beta.json()["detail"]["code"] == "FEATURE_NOT_CONFIGURED"


def test_admin_quota_override_and_global_settings(
    admin_client: tuple[TestClient, User],
    user_client: tuple[TestClient, User],
):
    aclient, admin = admin_client
    _, user = user_client

    fake_quota = FakeQuotaService()
    app.dependency_overrides[get_quota_service] = lambda: fake_quota
    app.dependency_overrides[get_optional_quota_service] = lambda: fake_quota

    try:
        # Set user quota override
        res_quota = aclient.patch(
            f"/api/v1/admin/users/{user.id}/quota",
            json={
                "scan_quota_override": 250,
                "reason": "VIP tournament participant",
            },
        )
        assert res_quota.status_code == 200

        # View global quota
        res_gquota = aclient.get("/api/v1/admin/settings/quota")
        assert res_gquota.status_code == 200
        assert res_gquota.json()["daily_scan_limit"] > 0

        # Update global quota
        res_upd_gquota = aclient.patch(
            "/api/v1/admin/settings/quota",
            json={
                "daily_scan_limit": 300,
                "hourly_scan_limit": 60,
                "reason": "Server scale-up",
            },
        )
        assert res_upd_gquota.status_code == 200
        assert res_upd_gquota.json()["daily_scan_limit"] == 300
    finally:
        app.dependency_overrides.pop(get_quota_service, None)
        app.dependency_overrides.pop(get_optional_quota_service, None)


def test_admin_beta_codes_management(admin_client: tuple[TestClient, User]):
    aclient, admin = admin_client

    fake_beta = FakeBetaService()
    app.dependency_overrides[get_beta_service] = lambda: fake_beta

    try:
        # Create code
        res_create = aclient.post(
            "/api/v1/admin/beta/codes",
            json={
                "label": "Beta Wave 1",
                "invitation_email": "pilot_tester@example.com",
                "max_uses": 3,
                "expires_days": 14,
            },
        )
        assert res_create.status_code == 200
        code_data = res_create.json()
        assert code_data["label"] == "Beta Wave 1"
        assert code_data["status"] == "active"
        code_id = code_data["id"]

        # List codes
        res_list = aclient.get("/api/v1/admin/beta/codes")
        assert res_list.status_code == 200
        assert res_list.json()["total"] >= 1

        # Revoke code
        res_revoke = aclient.patch(
            f"/api/v1/admin/beta/codes/{code_id}/revoke",
            json={"reason": "Revoking pilot wave"},
        )
        assert res_revoke.status_code == 200
        assert res_revoke.json()["status"] == "revoked"
    finally:
        app.dependency_overrides.pop(get_beta_service, None)


def test_admin_abuse_status(admin_client: tuple[TestClient, User]):
    aclient, _ = admin_client
    res = aclient.get("/api/v1/admin/abuse/status")
    assert res.status_code == 200
    data = res.json()
    assert "turnstile_enabled" in data
    assert "site_key" in data
    assert data["hard_rate_limit"] > 0
