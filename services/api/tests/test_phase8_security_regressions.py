import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem
from app.models.scan import Scan
from app.models.scan_session import ScanSession


def _register(client: TestClient, prefix: str) -> str:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{prefix}-{uuid.uuid4().hex}@example.com",
            "password": "DexLensUnpwnedPassword2026!",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


def _anonymous_session(client: TestClient) -> tuple[str, str]:
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200
    token = response.cookies.get("dexlens_session") or client.cookies.get(
        "dexlens_session"
    )
    assert token
    return response.json()["session_id"], token


def _scan(**overrides: object) -> Scan:
    values: dict[str, object] = {
        "id": str(uuid.uuid4()),
        "status": "uploaded",
        "image_path": f"{uuid.uuid4()}.jpg",
        "content_type": "image/jpeg",
        "width": 800,
        "height": 1100,
        "file_size": 100,
        "crop_status": "none",
        "crop_version": 0,
        "expires_at": datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2),
    }
    values.update(overrides)
    return Scan(**values)


def test_authenticated_user_cannot_read_or_mutate_anonymous_scan(
    client: TestClient, db: Session
):
    anonymous_client = TestClient(client.app)
    anonymous_session_id, _ = _anonymous_session(anonymous_client)
    scan = _scan(anonymous_session_id=anonymous_session_id)
    db.add(scan)
    db.commit()

    attacker = TestClient(client.app)
    _register(attacker, "scan-attacker")

    assert attacker.get(f"/api/v1/scans/{scan.id}").status_code == 404
    assert attacker.post(f"/api/v1/scans/{scan.id}/detect").status_code == 404
    crop_response = attacker.post(
        f"/api/v1/scans/{scan.id}/crop",
        json={
            "corners": {
                "top_left": {"x": 0, "y": 0},
                "top_right": {"x": 1, "y": 0},
                "bottom_right": {"x": 1, "y": 1},
                "bottom_left": {"x": 0, "y": 1},
            },
            "rotation": 0,
            "expected_version": 0,
        },
    )
    assert crop_response.status_code == 404


def test_anonymous_and_other_users_cannot_access_user_scan_session(
    client: TestClient, db: Session
):
    owner = TestClient(client.app)
    owner_id = _register(owner, "session-owner")
    scan_session = ScanSession(id=str(uuid.uuid4()), user_id=owner_id, status="active")
    db.add(scan_session)
    db.commit()

    anonymous = TestClient(client.app)
    _anonymous_session(anonymous)
    other_user = TestClient(client.app)
    _register(other_user, "session-other")

    for outsider in (anonymous, other_user):
        assert (
            outsider.get(f"/api/v1/scan-sessions/{scan_session.id}").status_code == 404
        )
        assert (
            outsider.post(
                f"/api/v1/scan-sessions/{scan_session.id}/complete"
            ).status_code
            == 404
        )


def test_feedback_requires_scan_ownership(client: TestClient, db: Session):
    owner = TestClient(client.app)
    owner_id = _register(owner, "feedback-owner")
    scan = _scan(user_id=owner_id)
    db.add(scan)
    db.commit()

    outsider = TestClient(client.app)
    _register(outsider, "feedback-outsider")
    payload = {"feedback_type": "correct_match"}
    assert (
        outsider.post(f"/api/v1/scans/{scan.id}/feedback", json=payload).status_code
        == 404
    )
    assert outsider.get(f"/api/v1/scans/{scan.id}/feedback").status_code == 404


def test_claim_requires_possession_of_anonymous_token(client: TestClient):
    source = TestClient(client.app)
    anonymous_session_id, _ = _anonymous_session(source)
    claimant = TestClient(client.app)
    _register(claimant, "claimant")

    response = claimant.post(
        "/api/v1/auth/claim-anonymous-session",
        json={
            "anonymous_session_id": anonymous_session_id,
            "anonymous_session_token": "not-the-source-session-token",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "INVALID_CLAIM_PROOF"


def test_registration_automatically_claims_current_anonymous_collection(
    client: TestClient, db: Session
):
    browser = TestClient(client.app)
    anonymous_session_id, _ = _anonymous_session(browser)
    item = CollectionItem(
        id=str(uuid.uuid4()),
        anonymous_session_id=anonymous_session_id,
        card_id="base1-58",
        set_id="base1",
        collector_number="58",
        card_name="Pikachu",
        set_name="Base Set",
        quantity=1,
        condition="near_mint",
        variant="normal",
        language="en",
        version=1,
    )
    db.add(item)
    db.commit()

    user_id = _register(browser, "registration-claim")
    db.refresh(item)
    assert item.user_id == user_id
    assert item.anonymous_session_id is None


def test_analytics_ignores_client_actor_session_and_rejects_foreign_scan(
    client: TestClient, db: Session
):
    owner = TestClient(client.app)
    owner_id = _register(owner, "analytics-owner")
    scan = _scan(user_id=owner_id)
    db.add(scan)
    db.commit()

    outsider = TestClient(client.app)
    _register(outsider, "analytics-outsider")
    response = outsider.post(
        "/api/v1/analytics/events",
        json={
            "event_name": "scan_processing_completed",
            "scan_id": scan.id,
            "session_id": "forged-session-id",
        },
    )
    assert response.status_code == 404


def test_database_rejects_duplicate_anonymous_grouping(client: TestClient, db: Session):
    anonymous_session_id, _ = _anonymous_session(client)
    common = {
        "anonymous_session_id": anonymous_session_id,
        "card_id": "base1-58",
        "set_id": "base1",
        "collector_number": "58",
        "card_name": "Pikachu",
        "set_name": "Base Set",
        "quantity": 1,
        "condition": "near_mint",
        "variant": "normal",
        "language": "en",
        "version": 1,
    }
    db.add(CollectionItem(id=str(uuid.uuid4()), **common))
    db.commit()
    db.add(CollectionItem(id=str(uuid.uuid4()), **common))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
    else:
        raise AssertionError("owner-aware grouping unique constraint was not enforced")


def test_live_session_does_not_report_another_users_collection(
    client: TestClient, db: Session
):
    viewer = TestClient(client.app)
    viewer_session_id, _ = _anonymous_session(viewer)
    other_user = TestClient(client.app)
    other_user_id = _register(other_user, "collection-owner")

    session = ScanSession(
        id=str(uuid.uuid4()),
        anonymous_session_id=viewer_session_id,
        status="active",
    )
    scan = _scan(
        anonymous_session_id=viewer_session_id,
        session_id=session.id,
        candidate_matches=[
            {
                "id": "base1-58",
                "name": "Pikachu",
                "local_id": "58",
                "set_id": "base1",
                "set_name": "Base Set",
                "score": 95,
                "reasons": ["Name match"],
            }
        ],
    )
    other_item = CollectionItem(
        id=str(uuid.uuid4()),
        user_id=other_user_id,
        card_id="base1-58",
        set_id="base1",
        collector_number="58",
        card_name="Pikachu",
        set_name="Base Set",
        quantity=7,
        condition="near_mint",
        variant="normal",
        language="en",
        version=1,
    )
    db.add_all([session, scan, other_item])
    db.commit()

    response = viewer.get(f"/api/v1/scan-sessions/{session.id}")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["in_collection"] is False
    assert item["collection_quantity"] == 0
    assert item["collection_item_id"] is None
