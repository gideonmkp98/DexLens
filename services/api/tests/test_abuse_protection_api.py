import io
import uuid

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.abuse import ScanAbuseService
from app.services.beta_service import DefaultBetaService
from app.services.turnstile import TurnstileService


def create_test_image_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (400, 560), color=(100, 150, 200))
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def reset_abuse_service():
    TurnstileService.reset_replay_cache()
    ScanAbuseService.reset()
    yield
    TurnstileService.reset_replay_cache()
    ScanAbuseService.reset()


def test_register_turnstile_success(client: TestClient):
    email = f"turnstile_user_{uuid.uuid4().hex[:6]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "ValidPassword123!",
            "turnstile_token": "test-pass-token",
        },
    )
    assert res.status_code == 201
    assert res.json()["email"] == email


def test_register_turnstile_invalid_token(client: TestClient):
    email = f"turnstile_fail_{uuid.uuid4().hex[:6]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "ValidPassword123!",
            "turnstile_token": "test-fail-token",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "INVALID_TOKEN"


def test_register_turnstile_expired_token(client: TestClient):
    email = f"turnstile_exp_{uuid.uuid4().hex[:6]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "ValidPassword123!",
            "turnstile_token": "test-expired-token",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "TOKEN_EXPIRED"


def test_register_turnstile_action_mismatch(client: TestClient):
    email = f"turnstile_action_{uuid.uuid4().hex[:6]}@example.com"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "ValidPassword123!",
            "turnstile_token": "test-action-scan",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "ACTION_MISMATCH"


def test_register_turnstile_replayed_token(client: TestClient):
    token = f"test-single-use-{uuid.uuid4().hex[:8]}"

    # First registration with token succeeds
    res1 = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"first_{uuid.uuid4().hex[:6]}@example.com",
            "password": "ValidPassword123!",
            "turnstile_token": token,
        },
    )
    assert res1.status_code == 201

    # Second registration with replayed token fails
    res2 = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"second_{uuid.uuid4().hex[:6]}@example.com",
            "password": "ValidPassword123!",
            "turnstile_token": token,
        },
    )
    assert res2.status_code == 403
    assert res2.json()["detail"]["code"] == "TOKEN_REPLAYED"


def test_register_turnstile_missing_when_enforced(client: TestClient):
    res = client.post(
        "/api/v1/auth/register",
        headers={"X-Enforce-Turnstile": "1"},
        json={
            "email": f"missing_{uuid.uuid4().hex[:6]}@example.com",
            "password": "ValidPassword123!",
        },
    )
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "MISSING_TOKEN"


def test_beta_claim_turnstile_protection(client: TestClient, db: Session):
    # Register/authenticate user first so valid user_id exists for redemption record
    email = f"beta_claimer_{uuid.uuid4().hex[:6]}@example.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    assert reg_res.status_code == 201

    beta_svc = DefaultBetaService(db)
    code_item = beta_svc.create_code(label="Invite Test", max_uses=5)

    # Missing token fails
    res_no_tok = client.post(
        "/api/v1/beta/claim",
        json={"code": code_item.code},
    )
    assert res_no_tok.status_code == 403
    assert res_no_tok.json()["detail"]["code"] == "MISSING_TOKEN"

    # Action mismatch fails (token intended for register used on beta)
    res_bad_action = client.post(
        "/api/v1/beta/claim",
        json={"code": code_item.code, "turnstile_token": "test-action-register"},
    )
    assert res_bad_action.status_code == 403
    assert res_bad_action.json()["detail"]["code"] == "ACTION_MISMATCH"

    # Valid token succeeds
    res_valid = client.post(
        "/api/v1/beta/claim",
        json={"code": code_item.code, "turnstile_token": "test-pass-token"},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["success"] is True


def test_scan_adaptive_abuse_challenge_flow(client: TestClient):
    client.cookies.clear()  # Anonymous client
    image_bytes = create_test_image_bytes()

    # Anonymous user uploads up to burst threshold (5)
    for _ in range(settings.SCAN_BURST_THRESHOLD):
        res = client.post(
            "/api/v1/scans",
            files={"file": ("card.jpg", image_bytes, "image/jpeg")},
        )
        assert res.status_code == 201

    # 6th rapid scan triggers CHALLENGE_REQUIRED
    res_burst = client.post(
        "/api/v1/scans",
        files={"file": ("card.jpg", image_bytes, "image/jpeg")},
    )
    assert res_burst.status_code == 403
    detail = res_burst.json()["detail"]
    assert detail["code"] == "CHALLENGE_REQUIRED"
    assert "site_key" in detail
    assert res_burst.headers.get("X-Challenge-Required") == "turnstile"

    # Solving challenge with valid token in header succeeds and resets burst
    res_solved = client.post(
        "/api/v1/scans",
        headers={"X-Turnstile-Token": "test-pass-token-scan"},
        files={"file": ("card.jpg", image_bytes, "image/jpeg")},
    )
    assert res_solved.status_code == 201


def test_scan_authenticated_user_low_friction(client: TestClient):
    email = f"scanner_{uuid.uuid4().hex[:6]}@example.com"
    reg_res = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Password123!"},
    )
    assert reg_res.status_code == 201

    image_bytes = create_test_image_bytes()

    # Authenticated user scans through normal threshold without challenge
    for _ in range(settings.SCAN_BURST_THRESHOLD + 2):
        res = client.post(
            "/api/v1/scans",
            files={"file": ("card.jpg", image_bytes, "image/jpeg")},
        )
        assert res.status_code == 201
