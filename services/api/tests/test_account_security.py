import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user import EmailVerification, User
from app.services.hibp import check_password_pwned


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# 1. Registration Extension & Policy Acceptance
# ---------------------------------------------------------------------------


def test_register_with_full_phase9_fields(client: TestClient, db: Session):
    tag = uuid.uuid4().hex[:8]
    username = f"trainer_{tag}"
    email = f"trainer_{tag}@example.com"
    password = "MyUnpwnedPassword2026!Valid"

    payload = {
        "username": username,
        "email": email,
        "password": password,
        "password_confirmation": password,
        "accepted_policies": True,
    }

    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == email
    assert data["username"] == username
    assert data["email_verified"] is False
    assert "id" in data

    # Verify database record
    user = db.query(User).filter(User.id == data["id"]).first()
    assert user is not None
    assert user.username == username
    assert user.email == email
    assert user.email_verified is False
    assert user.policies_accepted_at is not None

    # Verify verification token exists and is hashed with SHA-256
    verification = (
        db.query(EmailVerification).filter(EmailVerification.user_id == user.id).first()
    )
    assert verification is not None
    assert len(verification.token_hash) == 64
    assert re.match(r"^[0-9a-f]{64}$", verification.token_hash)
    assert verification.used_at is None
    assert verification.expires_at > _utcnow()


def test_register_refuses_when_policies_not_accepted(client: TestClient):
    tag = uuid.uuid4().hex[:8]
    payload = {
        "username": f"user_{tag}",
        "email": f"user_{tag}@example.com",
        "password": "MyUnpwnedPassword2026!Valid",
        "password_confirmation": "MyUnpwnedPassword2026!Valid",
        "accepted_policies": False,
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422


def test_register_refuses_when_password_confirmation_mismatches(
    client: TestClient,
):
    tag = uuid.uuid4().hex[:8]
    payload = {
        "username": f"user_{tag}",
        "email": f"user_{tag}@example.com",
        "password": "MyUnpwnedPassword2026!Valid",
        "password_confirmation": "DifferentPassword2026!Valid",
        "accepted_policies": True,
    }
    res = client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 2. Username & Email Normalization and Uniqueness
# ---------------------------------------------------------------------------


def test_username_normalization_and_case_insensitive_uniqueness(
    client: TestClient,
):
    tag = uuid.uuid4().hex[:6]
    original_username = f"AshKetchum_{tag}"
    email1 = f"ash_{tag}@example.com"
    password = "MyUnpwnedPassword2026!Valid"

    # Register first account with MixedCase username
    res1 = client.post(
        "/api/v1/auth/register",
        json={
            "username": original_username,
            "email": email1,
            "password": password,
            "password_confirmation": password,
            "accepted_policies": True,
        },
    )
    assert res1.status_code == 201
    assert res1.json()["username"] == original_username.lower()

    # Second account attempts lowercase version
    res2 = client.post(
        "/api/v1/auth/register",
        json={
            "username": original_username.lower(),
            "email": f"ash_two_{tag}@example.com",
            "password": password,
            "password_confirmation": password,
            "accepted_policies": True,
        },
    )
    assert res2.status_code == 400
    assert res2.json()["detail"]["code"] == "USERNAME_ALREADY_EXISTS"


def test_username_regex_validation(client: TestClient):
    valid_password = "MyUnpwnedPassword2026!Valid"

    # Too short (< 3)
    res_short = client.post(
        "/api/v1/auth/register",
        json={
            "username": "ab",
            "email": f"short_{uuid.uuid4().hex[:6]}@example.com",
            "password": valid_password,
        },
    )
    assert res_short.status_code == 422

    # Too long (> 30)
    res_long = client.post(
        "/api/v1/auth/register",
        json={
            "username": "a" * 31,
            "email": f"long_{uuid.uuid4().hex[:6]}@example.com",
            "password": valid_password,
        },
    )
    assert res_long.status_code == 422

    # Invalid special characters (spaces, @, !)
    for invalid_un in ["invalid name", "user@name", "user!name", "user.name"]:
        res_char = client.post(
            "/api/v1/auth/register",
            json={
                "username": invalid_un,
                "email": f"invalid_{uuid.uuid4().hex[:6]}@example.com",
                "password": valid_password,
            },
        )
        assert res_char.status_code == 422


def test_email_normalization_and_case_insensitive_uniqueness(
    client: TestClient,
):
    tag = uuid.uuid4().hex[:6]
    email = f"Trainer.{tag}@EXAMPLE.COM"
    password = "MyUnpwnedPassword2026!Valid"

    res1 = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"  {email}  ",
            "password": password,
        },
    )
    assert res1.status_code == 201
    assert res1.json()["email"] == email.lower()

    # Second attempt with same email in lowercase
    res2 = client.post(
        "/api/v1/auth/register",
        json={
            "email": email.lower(),
            "password": password,
        },
    )
    assert res2.status_code == 400
    assert res2.json()["detail"]["code"] == "EMAIL_ALREADY_EXISTS"


# ---------------------------------------------------------------------------
# 3. Modern Password Policy (NIST SP 800-63B)
# ---------------------------------------------------------------------------


def test_password_policy_minimum_15_characters(client: TestClient):
    email = f"policy_{uuid.uuid4().hex[:6]}@example.com"

    # 14 characters must fail
    res_14 = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "A" * 14,
        },
    )
    assert res_14.status_code == 422

    # 15 characters must pass
    res_15 = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Unpwned#Char15!",
        },
    )
    assert res_15.status_code == 201


def test_password_policy_supports_passphrases_with_spaces_and_unicode(
    client: TestClient,
):
    # Passphrase with spaces
    email1 = f"spaces_{uuid.uuid4().hex[:6]}@example.com"
    passphrase = "correct horse battery staple 2026 unpwned"
    res1 = client.post(
        "/api/v1/auth/register",
        json={"email": email1, "password": passphrase},
    )
    assert res1.status_code == 201

    # Passphrase with Unicode characters (Dutch accents, non-ASCII)
    email2 = f"unicode_{uuid.uuid4().hex[:6]}@example.com"
    unicode_pass = "Vóór-2026-Pokémon-Kaarten-Verzamelaar!"
    res2 = client.post(
        "/api/v1/auth/register",
        json={"email": email2, "password": unicode_pass},
    )
    assert res2.status_code == 201

    # Max length: supports at least 64 characters (tested with 100 characters)
    email3 = f"longpass_{uuid.uuid4().hex[:6]}@example.com"
    long_pass = "SecurePassphrase" * 6 + "End2026!"  # 104 chars
    res3 = client.post(
        "/api/v1/auth/register",
        json={"email": email3, "password": long_pass},
    )
    assert res3.status_code == 201


def test_password_policy_rejects_exceeding_128_characters(client: TestClient):
    email = f"toolong_{uuid.uuid4().hex[:6]}@example.com"
    too_long = "A" * 129
    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": too_long},
    )
    assert res.status_code == 422


# ---------------------------------------------------------------------------
# 4. Have I Been Pwned (HIBP) k-Anonymity Integration
# ---------------------------------------------------------------------------


def test_hibp_compromised_password_blocked(client: TestClient):
    # Common breached password (over 60+ breaches in HIBP)
    email = f"pwned_{uuid.uuid4().hex[:6]}@example.com"
    pwned_pass = "password12345678"  # >= 15 chars, but well-known breached

    res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": pwned_pass},
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["code"] == "PASSWORD_COMPROMISED"
    assert "Have I Been Pwned" in detail["message"]
    assert "breach_count" in detail
    assert detail["breach_count"] > 0


def test_hibp_k_anonymity_only_transmits_five_characters():
    """Verify that only the 5-char SHA-1 prefix is ever sent to the HIBP API."""
    password = "TestKAnonymityPassword2026!"
    full_sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix = full_sha1[:5]
    suffix = full_sha1[5:]

    with patch("httpx.Client.get") as mock_get:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = f"{suffix}:42\r\nOTHER_SUFFIX:1\r\n"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        is_pwned, count = check_password_pwned(password)
        assert is_pwned is True
        assert count == 42

        # Verify call arguments
        mock_get.assert_called_once()
        called_url = mock_get.call_args[0][0]
        assert called_url.endswith(f"/range/{prefix}")
        assert suffix not in called_url
        assert password not in called_url


def test_hibp_fail_open_strategy(client: TestClient):
    """When HIBP API is unreachable, default fail-open strategy allows registration."""
    email = f"failopen_{uuid.uuid4().hex[:6]}@example.com"
    password = "UniqueTestPassword2026#Valid"

    with patch("httpx.Client.get", side_effect=Exception("Network unreachable")):
        res = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert res.status_code == 201


def test_hibp_fail_closed_strategy():
    """When HIBP_FAIL_CLOSED=True, API unreachability blocks registration."""
    password = "UniqueTestPassword2026#Valid"
    with patch.object(settings, "HIBP_FAIL_CLOSED", True):
        with patch("httpx.Client.get", side_effect=Exception("Network timeout")):
            from app.services.hibp import PwnedPasswordsUnavailableError

            with pytest.raises(PwnedPasswordsUnavailableError):
                check_password_pwned(password)


# ---------------------------------------------------------------------------
# 5. Email Verification (Cryptographic Hashing, Expiry, Single-Use)
# ---------------------------------------------------------------------------


def test_email_verification_lifecycle(client: TestClient, db: Session):
    tag = uuid.uuid4().hex[:8]
    email = f"verify_{tag}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    with patch("app.services.auth.secrets.token_urlsafe") as mock_token:
        mock_raw_token = f"raw_secure_token_{tag}"
        mock_token.return_value = mock_raw_token

        res = client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )
        assert res.status_code == 201

    # Verify token in DB is hashed and not plaintext
    expected_hash = hashlib.sha256(mock_raw_token.encode("utf-8")).hexdigest()
    verification = (
        db.query(EmailVerification)
        .filter(EmailVerification.token_hash == expected_hash)
        .first()
    )
    assert verification is not None
    assert verification.used_at is None

    # 1. Verify email via POST /verify-email
    verify_res = client.post(
        "/api/v1/auth/verify-email",
        json={"token": mock_raw_token},
    )
    assert verify_res.status_code == 200
    assert "geverifieerd" in verify_res.json()["message"]

    # Verify user state in DB is now verified
    db.refresh(verification)
    assert verification.used_at is not None
    user = db.query(User).filter(User.id == verification.user_id).first()
    assert user.email_verified is True

    # 2. Single-use semantics: second attempt with same token must fail
    second_verify = client.post(
        "/api/v1/auth/verify-email",
        json={"token": mock_raw_token},
    )
    assert second_verify.status_code == 400
    assert second_verify.json()["detail"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


def test_email_verification_expired_token_rejected(client: TestClient, db: Session):
    tag = uuid.uuid4().hex[:8]
    email = f"expired_{tag}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    with patch("app.services.auth.secrets.token_urlsafe") as mock_token:
        mock_raw_token = f"expired_raw_token_{tag}"
        mock_token.return_value = mock_raw_token

        client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
        )

    # Manually expire the token in the database
    expected_hash = hashlib.sha256(mock_raw_token.encode("utf-8")).hexdigest()
    verification = (
        db.query(EmailVerification)
        .filter(EmailVerification.token_hash == expected_hash)
        .first()
    )
    verification.expires_at = _utcnow() - timedelta(hours=1)
    db.commit()

    # Verification attempt must be rejected
    verify_res = client.post(
        "/api/v1/auth/verify-email",
        json={"token": mock_raw_token},
    )
    assert verify_res.status_code == 400
    assert verify_res.json()["detail"]["code"] == "INVALID_OR_EXPIRED_TOKEN"


# ---------------------------------------------------------------------------
# 6. Resend Throttling & Non-Enumerating Responses
# ---------------------------------------------------------------------------


def test_resend_verification_throttling_and_non_enumeration(
    client: TestClient,
):
    tag = uuid.uuid4().hex[:8]
    email = f"resend_{tag}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    # 1. Immediate resend within 60s cooldown must be throttled with 429
    resend_fail = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": email},
    )
    assert resend_fail.status_code == 429
    assert resend_fail.json()["detail"]["code"] == "RESEND_THROTTLED"

    # 2. Non-existent email receives the exact same 200 OK message
    non_existent = client.post(
        "/api/v1/auth/resend-verification",
        json={"email": "nonexistent_collector_999@example.com"},
    )
    assert non_existent.status_code == 200
    assert "Als het e-mailadres bij ons bekend is" in non_existent.json()["message"]


# ---------------------------------------------------------------------------
# 7. Account Enumeration Prevention Across Flows
# ---------------------------------------------------------------------------


def test_login_does_not_enumerate_accounts(client: TestClient):
    registered_email = f"registered_{uuid.uuid4().hex[:6]}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    client.post(
        "/api/v1/auth/register",
        json={"email": registered_email, "password": password},
    )
    client.cookies.clear()

    # Existing account with wrong password
    bad_pass_res = client.post(
        "/api/v1/auth/login",
        json={"email": registered_email, "password": "WrongPassword2026!"},
    )
    assert bad_pass_res.status_code == 401
    assert bad_pass_res.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    # Non-existent account
    unknown_email_res = client.post(
        "/api/v1/auth/login",
        json={
            "email": "completely_unknown_999@example.com",
            "password": password,
        },
    )
    assert unknown_email_res.status_code == 401
    assert unknown_email_res.json()["detail"]["code"] == "INVALID_CREDENTIALS"

    # Both responses are completely indistinguishable
    assert (
        bad_pass_res.json()["detail"]["message"]
        == unknown_email_res.json()["detail"]["message"]
    )


def test_registration_non_enumeration_mode(client: TestClient):
    """When REGISTRATION_NON_ENUMERATION is enabled, duplicate email returns
    non-enumerating 200 response with dummy hashing.
    """
    tag = uuid.uuid4().hex[:8]
    email = f"duplicate_non_enum_{tag}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    # 1. First registration creates user
    res1 = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert res1.status_code == 201

    # 2. Second registration under non-enumeration setting returns uniform 200
    with patch.object(settings, "REGISTRATION_NON_ENUMERATION", True):
        with patch("app.api.v1.auth.dummy_verify_password") as mock_dummy:
            res2 = client.post(
                "/api/v1/auth/register",
                json={"email": email, "password": password},
            )
            assert res2.status_code == 200
            assert "verificatielink verstuurd" in res2.json()["message"]
            mock_dummy.assert_called_once()


# ---------------------------------------------------------------------------
# 8. Safe Rules for Changing Username
# ---------------------------------------------------------------------------


def test_change_username_rules_and_cooldown(client: TestClient, db: Session):
    tag = uuid.uuid4().hex[:6]
    user_client = TestClient(client.app)
    user_email = f"user_change_{tag}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    reg_res = user_client.post(
        "/api/v1/auth/register",
        json={
            "username": f"initial_{tag}",
            "email": user_email,
            "password": password,
        },
    )
    assert reg_res.status_code == 201

    # 1. Unauthenticated user cannot change username
    unauth_client = TestClient(client.app)
    unauth_res = unauth_client.patch(
        "/api/v1/auth/username",
        json={"username": f"new_un_{tag}"},
    )
    assert unauth_res.status_code == 401

    # 2. Successful username change
    new_username = f"updated_{tag}"
    patch_res = user_client.patch(
        "/api/v1/auth/username",
        json={"username": new_username},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["username"] == new_username

    # 3. Cooldown prevents immediate second change
    cooldown_res = user_client.patch(
        "/api/v1/auth/username",
        json={"username": f"another_{tag}"},
    )
    assert cooldown_res.status_code == 400
    assert cooldown_res.json()["detail"]["code"] == "USERNAME_COOLDOWN"
    assert "30 dagen" in cooldown_res.json()["detail"]["message"]


# ---------------------------------------------------------------------------
# 9. Safe Rules for Changing Email Address
# ---------------------------------------------------------------------------


def test_change_email_requires_password_and_verification(
    client: TestClient, db: Session
):
    tag = uuid.uuid4().hex[:6]
    user_client = TestClient(client.app)
    old_email = f"old_email_{tag}@example.com"
    password = "DexLensUnpwnedPassword2026!"

    reg_res = user_client.post(
        "/api/v1/auth/register",
        json={"email": old_email, "password": password},
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    new_email = f"new_email_{tag}@example.com"

    # 1. Wrong password rejected
    bad_pw_res = user_client.post(
        "/api/v1/auth/email/request-change",
        json={"new_email": new_email, "current_password": "WrongPassword999!"},
    )
    assert bad_pw_res.status_code == 401
    assert bad_pw_res.json()["detail"]["code"] == "INVALID_PASSWORD"

    # 2. Request change with correct password
    with patch("app.services.auth.secrets.token_urlsafe") as mock_token:
        mock_raw_token = f"email_change_raw_token_{tag}"
        mock_token.return_value = mock_raw_token

        req_res = user_client.post(
            "/api/v1/auth/email/request-change",
            json={
                "new_email": new_email,
                "current_password": password,
            },
        )
        assert req_res.status_code == 200
        assert "verificatielink verstuurd" in req_res.json()["message"]

    # Verify user email is NOT changed yet (unverified transition)
    user = db.query(User).filter(User.id == user_id).first()
    db.refresh(user)
    assert user.email == old_email

    # 3. Confirming the email verification token executes the change
    verify_res = client.post(
        "/api/v1/auth/verify-email",
        json={"token": mock_raw_token},
    )
    assert verify_res.status_code == 200

    # User email is now updated and verified
    db.refresh(user)
    assert user.email == new_email
    assert user.email_verified is True


# ---------------------------------------------------------------------------
# 10. Concurrency Safety
# ---------------------------------------------------------------------------


def test_concurrent_username_collision_gracefully_handled(
    client: TestClient, db: Session
):
    """Simulate race condition where two requests pass availability check
    simultaneously; database unique index catches collision.
    """
    tag = uuid.uuid4().hex[:6]
    shared_username = f"racer_{tag}"
    password = "DexLensUnpwnedPassword2026!"

    res1 = client.post(
        "/api/v1/auth/register",
        json={
            "username": shared_username,
            "email": f"racer1_{tag}@example.com",
            "password": password,
        },
    )
    assert res1.status_code == 201

    # Second registration with identical username caught by validation or DB
    res2 = client.post(
        "/api/v1/auth/register",
        json={
            "username": shared_username,
            "email": f"racer2_{tag}@example.com",
            "password": password,
        },
    )
    assert res2.status_code == 400
    assert res2.json()["detail"]["code"] == "USERNAME_ALREADY_EXISTS"
