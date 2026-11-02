from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.analytics import ProductAnalyticsEvent


def test_track_event_allowlisted(client: TestClient, db: Session):
    payload = {
        "event_name": "scan_started",
        "capture_mode": "auto",
        "device_category": "mobile",
        "browser_category": "safari_ios",
        "viewport_category": "compact",
        "metadata": {"feedback_type": "correct_match"},
    }
    response = client.post("/api/v1/analytics/events", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["event_name"] == "scan_started"
    assert "id" in data

    # Verify stored in DB
    event_id = data["id"]
    event_row = (
        db.query(ProductAnalyticsEvent)
        .filter(ProductAnalyticsEvent.id == event_id)
        .first()
    )
    assert event_row is not None
    assert event_row.capture_mode == "auto"
    assert event_row.device_category == "mobile"


def test_track_event_non_allowlisted_rejected(client: TestClient):
    payload = {
        "event_name": "unauthorized_custom_event_123",
        "capture_mode": "manual",
    }
    response = client.post("/api/v1/analytics/events", json=payload)
    assert response.status_code == 422


def test_track_event_forbidden_metadata_keys(client: TestClient):
    # Tests exclusion of raw_photo, ocr_text, image, etc.
    forbidden_keys = ["raw_photo", "ocr_text", "base64", "image"]
    for key in forbidden_keys:
        payload = {
            "event_name": "scan_started",
            "metadata": {key: "sample_payload"},
        }
        response = client.post("/api/v1/analytics/events", json=payload)
        assert response.status_code == 422


def test_track_event_rejects_non_allowlisted_metadata(client: TestClient):
    response = client.post(
        "/api/v1/analytics/events",
        json={
            "event_name": "scan_started",
            "metadata": {"email": "collector@example.com"},
        },
    )
    assert response.status_code == 422


def test_track_event_payload_size_limit(client: TestClient):
    # Metadata larger than 2KB should be rejected
    large_payload = {
        "event_name": "scan_started",
        "metadata": {"feedback_type": "x" * 2500},
    }
    response = client.post("/api/v1/analytics/events", json=large_payload)
    assert response.status_code == 422


def test_get_pilot_summary_metrics_authorized(client: TestClient):
    headers = {"X-Pilot-Admin-Token": settings.PILOT_ADMIN_SECRET}
    response = client.get("/api/v1/analytics/admin/summary", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "total_scans" in data
    assert "completion_rate" in data
    assert "top_candidate_acceptance_rate" in data
    assert "candidate_correction_rate" in data
    assert "capture_mode_distribution" in data
    assert "failure_categories" in data
    assert "total_feedback_count" in data
    assert "feedback_breakdown" in data


def test_get_pilot_summary_metrics_unauthorized(client: TestClient):
    # No header
    res1 = client.get("/api/v1/analytics/admin/summary")
    assert res1.status_code == 403

    # Wrong token header
    res2 = client.get(
        "/api/v1/analytics/admin/summary",
        headers={"X-Pilot-Admin-Token": "invalid_wrong_secret"},
    )
    assert res2.status_code == 403
