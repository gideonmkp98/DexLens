from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.email import InMemoryEmailProvider
from app.models.user import User
from app.schemas.beta_access import RegistrationMode
from app.services.beta_access import (
    BetaAccessService,
)
from tests.conftest import TestingSessionLocal


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def test_registration_mode_switching_and_status(client: TestClient):
    """Verify registration status endpoint reflects server registration mode."""
    BetaAccessService.reset_registration_mode()

    # 1. Default mode from settings
    resp = client.get("/api/v1/auth/registration-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "registration_mode" in data
    assert data["allows_open_registration"] is True

    # 2. Switch to beta_code_required
    BetaAccessService.set_registration_mode(RegistrationMode.BETA_CODE_REQUIRED)
    resp = client.get("/api/v1/auth/registration-status")
    data = resp.json()
    assert data["registration_mode"] == "beta_code_required"
    assert data["allows_open_registration"] is False
    assert data["requires_code_or_invite"] is True

    # 3. Switch to invite_only
    BetaAccessService.set_registration_mode(RegistrationMode.INVITE_ONLY)
    resp = client.get("/api/v1/auth/registration-status")
    data = resp.json()
    assert data["registration_mode"] == "invite_only"
    assert data["allows_open_registration"] is False
    assert data["requires_code_or_invite"] is True

    BetaAccessService.reset_registration_mode()


def test_registration_enforcement_open_mode(client: TestClient, db: Session):
    """In open mode, registration succeeds with or without credentials."""
    BetaAccessService.set_registration_mode(RegistrationMode.OPEN)

    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "open1@example.com", "password": "Password123!"},
    )
    assert resp.status_code == 201
    user_data = resp.json()
    assert user_data["email"] == "open1@example.com"
    assert user_data["has_beta_access"] is True

    BetaAccessService.reset_registration_mode()


def test_registration_enforcement_beta_code_required_mode(
    client: TestClient, db: Session
):
    """In beta_code_required mode, registration without a code or invite is blocked."""
    BetaAccessService.set_registration_mode(RegistrationMode.BETA_CODE_REQUIRED)
    service = BetaAccessService(db)

    # 1. Attempt registration without code -> 403
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "blocked@example.com", "password": "Password123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "REGISTRATION_BETA_CODE_REQUIRED"

    # 2. Attempt registration with invalid code -> 400
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "blocked@example.com",
            "password": "Password123!",
            "beta_code": "INVALID-CODE-XYZ",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_BETA_CODE"

    # 3. Create valid beta code and register -> 201
    code_obj, raw_code = service.create_beta_code(
        label="Test Wave",
        max_uses=5,
        scan_quota_allocated=25,
        beta_entitlement="wave1_tester",
    )
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "allowed@example.com",
            "password": "Password123!",
            "beta_code": raw_code,
        },
    )
    assert resp.status_code == 201
    user_data = resp.json()
    assert user_data["email"] == "allowed@example.com"
    assert user_data["has_beta_access"] is True
    assert user_data["beta_entitlement"] == "wave1_tester"
    assert user_data["scan_quota"] == 25

    # Verify code use count incremented
    db.refresh(code_obj)
    assert code_obj.used_count == 1

    BetaAccessService.reset_registration_mode()


def test_registration_enforcement_invite_only_mode(client: TestClient, db: Session):
    """In invite_only mode, only a valid invitation matching the email succeeds."""
    BetaAccessService.set_registration_mode(RegistrationMode.INVITE_ONLY)
    email_provider = InMemoryEmailProvider()
    service = BetaAccessService(db, email_provider=email_provider)

    # 1. Attempt registration without invite -> 403
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": "invitee@example.com", "password": "Password123!"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "REGISTRATION_INVITE_ONLY"

    # 2. Attempt registration with beta code in invite_only mode -> 403
    _, raw_code = service.create_beta_code(label="Beta Only")
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invitee@example.com",
            "password": "Password123!",
            "beta_code": raw_code,
        },
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "REGISTRATION_INVITE_ONLY"

    # 3. Create personal invite for invitee@example.com
    invitation, raw_token = service.create_invitation(
        email="invitee@example.com",
        scan_quota_allocated=100,
        beta_entitlement="vip_pilot",
    )

    # 4. Attempt registration with different email -> 400 INVITATION_EMAIL_MISMATCH
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "imposter@example.com",
            "password": "Password123!",
            "invite_token": raw_token,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVITATION_EMAIL_MISMATCH"

    # 5. Register with matching email -> 201
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "Invitee@example.com",  # mixed case should normalize
            "password": "Password123!",
            "invite_token": raw_token,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "invitee@example.com"
    assert data["has_beta_access"] is True
    assert data["beta_entitlement"] == "vip_pilot"
    assert data["scan_quota"] == 100

    # 6. Replay: attempt to register again with already accepted token -> 400
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "email": "invitee2@example.com",
            "password": "Password123!",
            "invite_token": raw_token,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "INVALID_INVITATION"

    BetaAccessService.reset_registration_mode()


def test_beta_code_expiry_and_revocation(client: TestClient, db: Session):
    """Verify expired and revoked beta codes are rejected."""
    service = BetaAccessService(db)

    # 1. Expired code
    expired_code, raw_expired = service.create_beta_code(
        label="Expired Wave",
        expires_at=_utcnow() - timedelta(hours=1),
    )
    valid, msg, _ = service.validate_beta_code(raw_expired)
    assert valid is False
    assert "verlopen" in msg

    # 2. Revoked code
    revoked_code, raw_revoked = service.create_beta_code(label="Revoked Wave")
    service.revoke_beta_code(revoked_code.id)
    valid, msg, _ = service.validate_beta_code(raw_revoked)
    assert valid is False
    assert "ingetrokken" in msg


def test_beta_code_email_restriction(client: TestClient, db: Session):
    """Verify beta code with allowed_email rejects mismatched emails."""
    service = BetaAccessService(db)
    _, raw_code = service.create_beta_code(
        label="VIP Direct",
        allowed_email="vip@domain.com",
    )

    # Validate against other email
    valid, msg, _ = service.validate_beta_code(raw_code, email="other@domain.com")
    assert valid is False
    assert "niet geldig voor dit e-mailadres" in msg

    # Validate against matching email
    valid, msg, _ = service.validate_beta_code(raw_code, email="VIP@DOMAIN.COM")
    assert valid is True


def test_invitation_expiry_revocation_and_resend(client: TestClient, db: Session):
    """Verify invitation lifecycle: expiration, revocation, and resend."""
    email_provider = InMemoryEmailProvider()
    service = BetaAccessService(db, email_provider=email_provider)

    # 1. Expired invitation
    invitation, raw_token = service.create_invitation(
        email="expired@test.com", expires_in_days=1
    )
    # Manually expire it in DB
    invitation.expires_at = _utcnow() - timedelta(minutes=5)
    db.commit()

    valid, msg, _ = service.validate_invitation(raw_token)
    assert valid is False
    assert "verlopen" in msg

    # 2. Revoked invitation
    inv2, token2 = service.create_invitation(email="revoked@test.com")
    service.revoke_invitation(inv2.id)
    valid, msg, _ = service.validate_invitation(token2)
    assert valid is False
    assert "ingetrokken" in msg

    # 3. Resend invitation invalidates prior token
    inv3, token3 = service.create_invitation(email="resend@test.com")
    assert len(email_provider.get_messages_for_email("resend@test.com")) == 1

    inv3_updated, token3_new = service.resend_invitation(inv3.id)
    assert token3 != token3_new
    assert inv3_updated.resend_count == 1
    assert len(email_provider.get_messages_for_email("resend@test.com")) == 2

    # Old token fails
    valid, _, _ = service.validate_invitation(token3)
    assert valid is False

    # New token succeeds
    valid, _, _ = service.validate_invitation(token3_new)
    assert valid is True


def test_beta_code_atomic_concurrency_no_over_redemption(db: Session):
    """Concurrent threads attempting to redeem a code with max_uses=3.

    Guarantees: Exactly 3 succeed, remaining fail with exhaustion, used_count == 3.
    """
    service = BetaAccessService(db)
    max_limit = 3
    total_threads = 10

    code_obj, raw_code = service.create_beta_code(
        label="Concurrency Test",
        max_uses=max_limit,
    )

    # Pre-create 10 users to attempt redemption
    users = []
    for i in range(total_threads):
        user = User(
            email=f"concurrent_user_{i}@test.com",
            password_hash="test",
            role="user",
            is_active=True,
        )
        db.add(user)
    db.commit()
    for u in users:
        db.refresh(u)

    user_ids = [
        u.id
        for u in db.query(User)
        .filter(User.email.like("concurrent_user_%@test.com"))
        .all()
    ]
    assert len(user_ids) == total_threads

    successes = []
    failures = []

    def _attempt_redemption(uid: str):
        # Dedicated DB session per thread to simulate true concurrent clients
        thread_db = TestingSessionLocal()
        thread_service = BetaAccessService(thread_db)
        try:
            target_user = thread_db.query(User).filter(User.id == uid).first()
            thread_service.redeem_beta_code(raw_code, target_user)
            successes.append(uid)
        except Exception as exc:
            failures.append(str(exc))
        finally:
            thread_db.close()

    with ThreadPoolExecutor(max_workers=total_threads) as executor:
        list(executor.map(_attempt_redemption, user_ids))

    assert len(successes) == max_limit
    assert len(failures) == (total_threads - max_limit)

    db.commit()
    db.refresh(code_obj)
    assert code_obj.used_count == max_limit


def test_invitation_concurrency_single_use(db: Session):
    """Concurrent threads attempting to redeem the exact same invitation token.

    Guarantees: Exactly 1 succeeds, other fails (single-use token protection).
    """
    email_provider = InMemoryEmailProvider()
    service = BetaAccessService(db, email_provider=email_provider)

    target_email = "singleuse@test.com"
    _, raw_token = service.create_invitation(email=target_email)

    user1 = User(
        email=target_email,
        password_hash="test",
        role="user",
        is_active=True,
    )
    db.add(user1)
    db.commit()
    db.refresh(user1)

    results = []

    def _attempt_redeem(worker_idx: int):
        t_db = TestingSessionLocal()
        t_service = BetaAccessService(t_db)
        try:
            u = t_db.query(User).filter(User.id == user1.id).first()
            t_service.redeem_invitation(raw_token, u)
            results.append("success")
        except Exception:
            results.append("failure")
        finally:
            t_db.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(_attempt_redeem, [1, 2]))

    assert results.count("success") == 1
    assert results.count("failure") == 1


def test_admin_api_authorization_and_token_leakage(client: TestClient, db: Session):
    """Verify admin endpoints require auth and never leak secret tokens."""
    # 1. Unauthenticated request -> 403
    resp = client.get("/api/v1/admin/beta-codes")
    assert resp.status_code == 403

    admin_headers = {"X-Pilot-Admin-Token": settings.PILOT_ADMIN_SECRET}

    # 2. Create beta code via Admin API
    resp = client.post(
        "/api/v1/admin/beta-codes",
        headers=admin_headers,
        json={"label": "Admin Launch Wave", "max_uses": 50},
    )
    assert resp.status_code == 201
    created_code = resp.json()
    assert "code" in created_code
    plain_secret = created_code["code"]
    code_id = created_code["id"]

    # 3. List beta codes -> plaintext code secret MUST NOT be present
    resp = client.get("/api/v1/admin/beta-codes", headers=admin_headers)
    assert resp.status_code == 200
    listing = resp.json()["items"]
    found = next((item for item in listing if item["id"] == code_id), None)
    assert found is not None
    assert "code" not in found
    assert "code_prefix" in found
    assert plain_secret not in str(resp.json())

    # 4. Create personal invitation via Admin API
    resp = client.post(
        "/api/v1/admin/invitations",
        headers=admin_headers,
        json={"email": "pilot_admin_invite@example.com"},
    )
    assert resp.status_code == 201
    created_invite = resp.json()
    assert "token" not in created_invite  # Token never exposed in API response
    assert created_invite["email"] == "pilot_admin_invite@example.com"
    invite_id = created_invite["id"]

    # 5. List invitations -> token MUST NOT be present
    resp = client.get("/api/v1/admin/invitations", headers=admin_headers)
    assert resp.status_code == 200
    inv_listing = resp.json()["items"]
    inv_found = next((i for i in inv_listing if i["id"] == invite_id), None)
    assert inv_found is not None
    assert "token" not in inv_found
    assert "token_hash" not in inv_found

    # 6. Revoke beta code and invitation via Admin API
    resp = client.post(
        f"/api/v1/admin/beta-codes/{code_id}/revoke", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False

    resp = client.post(
        f"/api/v1/admin/invitations/{invite_id}/revoke", headers=admin_headers
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "revoked"


def test_public_validation_endpoints(client: TestClient, db: Session):
    """Verify public validation endpoints for form UX."""
    service = BetaAccessService(db)
    _, raw_code = service.create_beta_code(label="UX Test Code")
    _, raw_token = service.create_invitation(email="ux_tester@test.com")

    # 1. Valid code
    resp = client.post("/api/v1/auth/validate-beta-code", json={"code": raw_code})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert resp.json()["label"] == "UX Test Code"

    # 2. Invalid code
    resp = client.post("/api/v1/auth/validate-beta-code", json={"code": "INVALID-CODE"})
    assert resp.status_code == 200
    assert resp.json()["valid"] is False

    # 3. Valid invitation
    resp = client.post("/api/v1/auth/validate-invitation", json={"token": raw_token})
    assert resp.status_code == 200
    assert resp.json()["valid"] is True
    assert "u***r@test.com" == resp.json()["masked_email"]

    # 4. Invalid invitation
    resp = client.post(
        "/api/v1/auth/validate-invitation", json={"token": "invalid-token-123456"}
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is False
