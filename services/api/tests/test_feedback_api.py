import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.feedback import ScanFeedback
from app.models.scan import Scan


def _create_test_scan(client: TestClient, db: Session) -> Scan:
    session_id = client.get("/api/v1/auth/me").json()["session_id"]
    scan = Scan(
        id=str(uuid.uuid4()),
        anonymous_session_id=session_id,
        status="confirmed",
        image_path="/app/uploads/scans/feedback_test.jpg",
        content_type="image/jpeg",
        width=800,
        height=1100,
        file_size=150000,
        expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=2),
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def test_submit_and_get_scan_feedback(client: TestClient, db: Session):
    scan = _create_test_scan(client, db)

    payload = {
        "feedback_type": "correct_match",
        "suggested_card_id": "base1-4",
        "selected_card_id": "base1-4",
        "confidence_state": "high",
        "selected_in_candidates": True,
        "notes": "Spot on identification!",
        "device_category": "mobile",
    }
    response = client.post(f"/api/v1/scans/{scan.id}/feedback", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["scan_id"] == scan.id
    assert data["feedback_type"] == "correct_match"
    assert data["notes"] == "Spot on identification!"

    # Retrieve feedback
    get_res = client.get(f"/api/v1/scans/{scan.id}/feedback")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == data["id"]
    assert get_res.json()["feedback_type"] == "correct_match"


def test_submit_scan_feedback_idempotent_update(client: TestClient, db: Session):
    scan = _create_test_scan(client, db)

    payload1 = {
        "feedback_type": "wrong_card",
        "suggested_card_id": "base1-1",
        "selected_card_id": "base1-2",
        "confidence_state": "medium",
        "notes": "Initial remark",
    }
    res1 = client.post(f"/api/v1/scans/{scan.id}/feedback", json=payload1)
    assert res1.status_code == 201
    feedback_id = res1.json()["id"]

    # Re-submit feedback for the same scan in the same session
    payload2 = {
        "feedback_type": "in_alternatives",
        "suggested_card_id": "base1-1",
        "selected_card_id": "base1-3",
        "confidence_state": "medium",
        "notes": "Updated remark: found in alternatives list",
    }
    res2 = client.post(f"/api/v1/scans/{scan.id}/feedback", json=payload2)
    assert res2.status_code in (200, 201)
    assert res2.json()["id"] == feedback_id
    assert res2.json()["feedback_type"] == "in_alternatives"
    assert res2.json()["notes"] == "Updated remark: found in alternatives list"

    # Verify only 1 row exists in database for this scan
    count = db.query(ScanFeedback).filter(ScanFeedback.scan_id == scan.id).count()
    assert count == 1


def test_submit_feedback_nonexistent_scan(client: TestClient):
    non_existent_id = str(uuid.uuid4())
    payload = {
        "feedback_type": "correct_match",
    }
    res = client.post(f"/api/v1/scans/{non_existent_id}/feedback", json=payload)
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "SCAN_NOT_FOUND"


def test_get_feedback_nonexistent(client: TestClient, db: Session):
    scan = _create_test_scan(client, db)
    res = client.get(f"/api/v1/scans/{scan.id}/feedback")
    assert res.status_code == 404
