from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from app.core.config import settings
from app.services.abuse import (
    ScanAbuseService,
    ScanChallengeRequiredError,
    ScanRateLimitExceededError,
)
from app.services.audit import sanitize_audit_metadata
from app.services.turnstile import TurnstileService


@pytest.fixture(autouse=True)
def reset_services():
    TurnstileService.reset_replay_cache()
    ScanAbuseService.reset()
    yield
    TurnstileService.reset_replay_cache()
    ScanAbuseService.reset()


def test_turnstile_missing_token():
    result = TurnstileService.verify(token=None, expected_action="register")
    assert not result.success
    assert result.error_code == "MISSING_TOKEN"


def test_turnstile_valid_test_token():
    result = TurnstileService.verify(
        token="test-pass-token-123",
        expected_action="register",
    )
    assert result.success
    assert result.action == "register"


def test_turnstile_invalid_test_token():
    result = TurnstileService.verify(
        token="test-fail-token",
        expected_action="register",
    )
    assert not result.success
    assert result.error_code == "INVALID_TOKEN"


def test_turnstile_expired_token():
    result = TurnstileService.verify(
        token="test-expired-token",
        expected_action="register",
    )
    assert not result.success
    assert result.error_code == "TOKEN_EXPIRED"


def test_turnstile_action_mismatch():
    result = TurnstileService.verify(
        token="test-action-scan",
        expected_action="register",
    )
    assert not result.success
    assert result.error_code == "ACTION_MISMATCH"


def test_turnstile_single_use_replay_prevention():
    token = "test-unique-token-abc"
    # First use succeeds
    result1 = TurnstileService.verify(token=token, expected_action="scan")
    assert result1.success

    # Second use of identical token fails as replayed
    result2 = TurnstileService.verify(token=token, expected_action="scan")
    assert not result2.success
    assert result2.error_code == "TOKEN_REPLAYED"


def test_trusted_proxy_ip_extraction():
    # Peer is NOT trusted
    req_untrusted = MagicMock(spec=Request)
    req_untrusted.client = MagicMock(host="10.0.0.1")
    req_untrusted.headers = {"x-forwarded-for": "198.51.100.5, 10.0.0.1"}

    assert TurnstileService.get_trusted_client_ip(req_untrusted) == "10.0.0.1"

    # Peer IS trusted
    orig_trusted = settings.TRUSTED_PROXY_IPS
    try:
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1", "10.0.0.1"]
        assert TurnstileService.get_trusted_client_ip(req_untrusted) == "198.51.100.5"
    finally:
        settings.TRUSTED_PROXY_IPS = orig_trusted


def test_audit_metadata_sanitization():
    unsafe_metadata = {
        "user_id": "usr-123",
        "new_status": "suspended",
        "password": "super-secret-password",
        "password_hash": "$argon2id$...dummy",
        "nested": {
            "session_token": "raw-token-abc",
            "reason": "Abusive behavior",
            "api_key_secret": "sk-12345",
        },
        "safe_list": ["ok1", {"auth_token": "leak", "clean": "fine"}],
    }

    cleaned = sanitize_audit_metadata(unsafe_metadata)
    assert "password" not in cleaned
    assert "password_hash" not in cleaned
    assert cleaned["user_id"] == "usr-123"
    assert cleaned["new_status"] == "suspended"
    assert "session_token" not in cleaned["nested"]
    assert "api_key_secret" not in cleaned["nested"]
    assert cleaned["nested"]["reason"] == "Abusive behavior"
    assert "auth_token" not in cleaned["safe_list"][1]
    assert cleaned["safe_list"][1]["clean"] == "fine"


def test_adaptive_scan_abuse_burst_and_recovery():
    req = MagicMock(spec=Request)
    req.client = MagicMock(host="192.0.2.1")
    req.headers = {}

    # Anonymous user scans up to threshold (first 5 scans pass freely)
    for _ in range(settings.SCAN_BURST_THRESHOLD):
        ScanAbuseService.check_and_record_scan(
            request=req,
            user_id=None,
            turnstile_token=None,
        )

    # 6th scan triggers challenge required
    with pytest.raises(ScanChallengeRequiredError) as exc_info:
        ScanAbuseService.check_and_record_scan(
            request=req,
            user_id=None,
            turnstile_token=None,
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["code"] == "CHALLENGE_REQUIRED"

    # Solving challenge with valid turnstile token allows scan and resets burst window
    ScanAbuseService.check_and_record_scan(
        request=req,
        user_id=None,
        turnstile_token="test-turnstile-solution-1",
    )

    # Subsequent scan can now proceed
    ScanAbuseService.check_and_record_scan(
        request=req,
        user_id=None,
        turnstile_token=None,
    )


def test_authenticated_user_low_friction():
    req = MagicMock(spec=Request)
    req.client = MagicMock(host="192.0.2.2")
    req.headers = {}

    # Authenticated user scans without needing Turnstile under normal usage
    for _ in range(settings.SCAN_BURST_THRESHOLD + 2):
        ScanAbuseService.check_and_record_scan(
            request=req,
            user_id="auth-user-999",
            turnstile_token=None,
        )


def test_independent_hard_rate_limit():
    req = MagicMock(spec=Request)
    req.client = MagicMock(host="192.0.2.3")
    req.headers = {}

    # Fill rate limit window up to limit
    for i in range(settings.SCAN_HARD_RATE_LIMIT_PER_MINUTE):
        ScanAbuseService.check_and_record_scan(
            request=req,
            user_id=f"user-{i}",
            turnstile_token=f"test-tok-{i}",
        )

    # Exceeding hard limit raises 429
    with pytest.raises(ScanRateLimitExceededError) as exc_info:
        ScanAbuseService.check_and_record_scan(
            request=req,
            user_id="user-overflow",
            turnstile_token="test-tok-overflow",
        )
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "RATE_LIMIT_EXCEEDED"
