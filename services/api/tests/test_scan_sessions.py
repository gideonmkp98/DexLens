import io
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.models.collection import CollectionItem, CollectionScanLink
from app.models.scan import Scan
from app.models.scan_session import ScanSession
from app.schemas.scan import CandidateMatchItem
from app.services.card_detector import CropCorners, Point
from app.services.ocr.normalizer import CardExtractionResult
from app.services.scan_session import (
    ScanSessionService,
    SessionClosedError,
    SessionNotFoundError,
)


def _create_test_image(size: tuple[int, int] = (600, 800), color: str = "red") -> bytes:
    """Generate in-memory JPEG image bytes for tests."""
    buf = io.BytesIO()
    img = Image.new("RGB", size, color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ==============================================================================
# Model & Database Constraints Tests
# ==============================================================================


def test_scan_session_model_crud(db: Session):
    """Test ScanSession creation, updates, and database defaults."""
    session = ScanSession()
    db.add(session)
    db.commit()
    db.refresh(session)

    assert session.id is not None
    assert len(session.id) == 36
    assert session.status == "active"
    assert session.created_at is not None
    assert session.updated_at is not None
    assert session.completed_at is None
    assert "ScanSession" in repr(session)

    # Transition to completed
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    session.status = "completed"
    session.completed_at = now_utc
    db.commit()
    db.refresh(session)

    assert session.status == "completed"
    assert session.completed_at is not None


def test_scan_session_check_constraint_invalid_status(db: Session):
    """Test check constraint ck_scan_sessions_status enforces allowed statuses."""
    invalid_session = ScanSession(status="invalid_status")
    db.add(invalid_session)
    with pytest.raises((IntegrityError, OperationalError)):
        db.commit()
    db.rollback()


def test_scan_session_relationship_with_scans(db: Session):
    """Test Scan-ScanSession foreign key and reverse relationship."""
    session = ScanSession(status="active")
    db.add(session)
    db.commit()

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    scan1 = Scan(
        id=str(uuid.uuid4()),
        session_id=session.id,
        image_path="scan1.jpg",
        content_type="image/jpeg",
        width=400,
        height=600,
        file_size=50000,
        created_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
    )
    scan2 = Scan(
        id=str(uuid.uuid4()),
        session_id=session.id,
        image_path="scan2.jpg",
        content_type="image/jpeg",
        width=400,
        height=600,
        file_size=60000,
        created_at=now_utc + timedelta(seconds=5),
        expires_at=now_utc + timedelta(hours=24),
    )
    db.add_all([scan1, scan2])
    db.commit()

    db.refresh(session)
    assert len(session.scans) == 2
    assert session.scans[0].id == scan1.id
    assert session.scans[1].id == scan2.id
    assert scan1.session.id == session.id

    # Test ON DELETE SET NULL behavior
    db.delete(session)
    db.commit()

    db.refresh(scan1)
    db.refresh(scan2)
    assert scan1.session_id is None
    assert scan2.session_id is None


# ==============================================================================
# Domain Service Tests
# ==============================================================================


def test_service_create_session(db: Session):
    """Test ScanSessionService.create_session domain method."""
    service = ScanSessionService(db=db)
    response = service.create_session()

    assert response.id is not None
    assert response.status == "active"
    assert response.total_scans == 0
    assert response.completed_at is None


@pytest.mark.asyncio
async def test_service_get_session_not_found(db: Session):
    """Test get_session with non-existent session raises SessionNotFoundError."""
    service = ScanSessionService(db=db)
    with pytest.raises(SessionNotFoundError) as exc_info:
        await service.get_session(str(uuid.uuid4()))
    assert exc_info.value.code == "SESSION_NOT_FOUND"
    assert exc_info.value.status_code == 404


def test_service_complete_session_idempotent(db: Session):
    """Test complete_session transitions to completed and is idempotent."""
    service = ScanSessionService(db=db)
    created = service.create_session()

    completed1 = service.complete_session(created.id)
    assert completed1.status == "completed"
    assert completed1.completed_at is not None

    completed2 = service.complete_session(created.id)
    assert completed2.status == "completed"
    assert completed2.completed_at == completed1.completed_at


def test_service_complete_session_not_found(db: Session):
    """Test complete_session with invalid ID raises SessionNotFoundError."""
    service = ScanSessionService(db=db)
    with pytest.raises(SessionNotFoundError):
        service.complete_session(str(uuid.uuid4()))


@pytest.mark.asyncio
async def test_service_capture_frame_session_closed(db: Session):
    """Test capture_frame into completed session raises SessionClosedError."""
    service = ScanSessionService(db=db)
    created = service.create_session()
    service.complete_session(created.id)

    with pytest.raises(SessionClosedError) as exc_info:
        await service.capture_frame(
            session_id=created.id,
            image_input=_create_test_image(),
        )
    assert exc_info.value.code == "SESSION_NOT_ACTIVE"
    assert exc_info.value.status_code == 409


# ==============================================================================
# API Endpoints Tests
# ==============================================================================


def test_api_create_scan_session(client: TestClient):
    """POST /api/v1/scan-sessions creates an active session."""
    response = client.post("/api/v1/scan-sessions", json={})
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["status"] == "active"
    assert data["total_scans"] == 0
    assert data["completed_at"] is None


def test_api_get_scan_session_empty(client: TestClient):
    """GET /api/v1/scan-sessions/{id} returns empty list of items for new session."""
    create_resp = client.post("/api/v1/scan-sessions")
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    response = client.get(f"/api/v1/scan-sessions/{session_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == session_id
    assert data["status"] == "active"
    assert data["total_scans"] == 0
    assert data["items"] == []


def test_api_get_scan_session_invalid_uuid(client: TestClient):
    """GET /api/v1/scan-sessions/{id} with non-UUID returns 404."""
    response = client.get("/api/v1/scan-sessions/not-a-valid-uuid")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SESSION_NOT_FOUND"


def test_api_get_scan_session_not_found(client: TestClient):
    """GET /api/v1/scan-sessions/{id} with non-existent UUID returns 404."""
    random_uuid = str(uuid.uuid4())
    response = client.get(f"/api/v1/scan-sessions/{random_uuid}")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "SESSION_NOT_FOUND"


def test_api_get_scan_session_with_scans_and_collection(
    client: TestClient, db: Session
):
    """GET /api/v1/scan-sessions/{id} returns scans with collection status."""
    # 1. Create session
    session = ScanSession(status="active")
    db.add(session)
    db.commit()

    # 2. Add an item to collection (Pikachu)
    collection_item = CollectionItem(
        id=str(uuid.uuid4()),
        card_id="base1-58",
        provider="tcgdex",
        card_name="Pikachu",
        set_id="base1",
        set_name="Base Set",
        collector_number="58",
        quantity=3,
        language="en",
        variant="normal",
        condition="near_mint",
    )
    db.add(collection_item)
    db.commit()

    # 3. Add scans to the session
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    # Scan 1: Confirmed card that matches collection item
    scan1 = Scan(
        id=str(uuid.uuid4()),
        session_id=session.id,
        status="confirmed",
        image_path="scan1.jpg",
        content_type="image/jpeg",
        width=500,
        height=700,
        file_size=80000,
        crop_status="confirmed",
        crop_path="scan1_crop.jpg",
        crop_version=1,
        confirmed_card_id="base1-58",
        confirmed_card_name="Pikachu",
        confirmed_card_number="58",
        confirmed_card_set_name="Base Set",
        card_confirmed_at=now_utc,
        created_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
    )
    # Scan 2: Unconfirmed card, not in collection
    scan2 = Scan(
        id=str(uuid.uuid4()),
        session_id=session.id,
        status="uploaded",
        image_path="scan2.jpg",
        content_type="image/jpeg",
        width=500,
        height=700,
        file_size=75000,
        crop_status="none",
        candidate_matches=[
            {
                "id": "base1-4",
                "name": "Charizard",
                "local_id": "4",
                "set_id": "base1",
                "set_name": "Base Set",
                "score": 95,
                "reasons": ["Name match"],
            }
        ],
        created_at=now_utc + timedelta(seconds=10),
        expires_at=now_utc + timedelta(hours=24),
    )
    # Scan 3: Directly linked via CollectionScanLink
    scan3 = Scan(
        id=str(uuid.uuid4()),
        session_id=session.id,
        status="confirmed",
        image_path="scan3.jpg",
        content_type="image/jpeg",
        width=500,
        height=700,
        file_size=90000,
        crop_status="confirmed",
        crop_path="scan3_crop.jpg",
        crop_version=1,
        confirmed_card_id="base1-1",
        confirmed_card_name="Alakazam",
        confirmed_card_number="1",
        confirmed_card_set_name="Base Set",
        card_confirmed_at=now_utc,
        created_at=now_utc + timedelta(seconds=20),
        expires_at=now_utc + timedelta(hours=24),
    )
    db.add_all([scan1, scan2, scan3])
    db.flush()

    # Link scan3 to a collection item
    item3 = CollectionItem(
        id=str(uuid.uuid4()),
        card_id="base1-1",
        provider="tcgdex",
        card_name="Alakazam",
        set_id="base1",
        set_name="Base Set",
        collector_number="1",
        quantity=1,
        language="en",
        variant="normal",
        condition="near_mint",
    )
    db.add(item3)
    db.flush()
    link3 = CollectionScanLink(scan_id=scan3.id, collection_item_id=item3.id)
    db.add(link3)
    db.commit()

    # 4. Fetch session details via API
    response = client.get(f"/api/v1/scan-sessions/{session.id}")
    assert response.status_code == 200
    data = response.json()

    assert data["total_scans"] == 3
    items = data["items"]
    assert len(items) == 3

    # Scan 1 checks
    assert items[0]["scan_id"] == scan1.id
    assert items[0]["in_collection"] is True
    assert items[0]["collection_quantity"] == 3
    assert items[0]["collection_item_id"] == collection_item.id
    assert items[0]["crop_image_url"] == f"/api/v1/scans/{scan1.id}/crop/image?v=1"

    # Scan 2 checks
    assert items[1]["scan_id"] == scan2.id
    assert items[1]["in_collection"] is False
    assert items[1]["collection_quantity"] == 0
    assert items[1]["collection_item_id"] is None
    assert items[1]["best_match"]["name"] == "Charizard"

    # Scan 3 checks (directly linked)
    assert items[2]["scan_id"] == scan3.id
    assert items[2]["in_collection"] is True
    assert items[2]["collection_quantity"] == 1
    assert items[2]["collection_item_id"] == item3.id


def test_api_complete_scan_session(client: TestClient):
    """POST /api/v1/scan-sessions/{id}/complete marks session completed."""
    create_resp = client.post("/api/v1/scan-sessions")
    session_id = create_resp.json()["id"]

    response = client.post(f"/api/v1/scan-sessions/{session_id}/complete")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == session_id
    assert data["status"] == "completed"
    assert data["completed_at"] is not None

    # Idempotent second call
    resp2 = client.post(f"/api/v1/scan-sessions/{session_id}/complete")
    assert resp2.status_code == 200
    assert resp2.json()["status"] == "completed"


def test_api_capture_frame_success(client: TestClient, db: Session):
    """POST /api/v1/scan-sessions/{id}/capture processes live frame with detection."""
    create_resp = client.post("/api/v1/scan-sessions")
    session_id = create_resp.json()["id"]

    image_bytes = _create_test_image(size=(800, 1100), color="blue")
    files = {"file": ("frame.jpg", image_bytes, "image/jpeg")}

    fake_corners = CropCorners(
        top_left=Point(x=0.1, y=0.1),
        top_right=Point(x=0.9, y=0.1),
        bottom_right=Point(x=0.9, y=0.9),
        bottom_left=Point(x=0.1, y=0.9),
    )

    fake_candidate = CandidateMatchItem(
        id="base1-4",
        name="Charizard",
        local_id="4",
        set_id="base1",
        set_name="Base Set",
        image_url="https://assets.tcgdex.net/en/base/base1/4",
        score=98,
        reasons=["Name match", "Collector number match"],
    )

    extraction_result = CardExtractionResult(
        raw_text="Charizard 120 HP 4/102",
        name="Charizard",
        number="4/102",
        local_id="4",
        printed_denominator="102",
        set_code="base1",
        confidence=95.0,
    )

    with (
        patch(
            "app.services.scan_session.detect_card_corners",
            return_value=(True, fake_corners, "Card detected", 0.95),
        ),
        patch(
            "app.services.scan_session.perform_crop_and_warp",
            return_value=(600, 840, 120000),
        ),
        patch(
            "app.services.scan_session.recognize_card_image",
            return_value=extraction_result,
        ),
        patch(
            "app.services.scan_session.retrieve_and_rank_candidates",
            new_callable=AsyncMock,
            return_value=([fake_candidate], 1),
        ),
        patch(
            "app.services.scan_session.rerank_by_artwork",
            new_callable=AsyncMock,
            side_effect=lambda crop_path, cands: cands,
        ),
    ):
        response = client.post(
            f"/api/v1/scan-sessions/{session_id}/capture", files=files
        )
        assert response.status_code == 200
        data = response.json()

        assert data["session_id"] == session_id
        assert data["session_status"] == "active"
        assert data["detected"] is True
        assert data["corners"] is not None
        assert len(data["candidates"]) == 1
        assert data["candidates"][0]["name"] == "Charizard"
        assert data["best_match"]["name"] == "Charizard"
        assert "scan" in data
        assert data["scan"]["crop_status"] == "confirmed"

        # Verify DB scan record
        scan_record = db.query(Scan).filter(Scan.id == data["scan"]["id"]).first()
        assert scan_record is not None
        assert scan_record.session_id == session_id
        assert scan_record.recognized_name == "Charizard"


def test_api_capture_frame_not_detected_fallback(client: TestClient):
    """POST /api/v1/scan-sessions/{id}/capture gracefully handles frame without card."""
    create_resp = client.post("/api/v1/scan-sessions")
    session_id = create_resp.json()["id"]

    image_bytes = _create_test_image()
    files = {"file": ("frame.jpg", image_bytes, "image/jpeg")}

    with patch(
        "app.services.scan_session.detect_card_corners",
        return_value=(False, None, "No card detected", 0.0),
    ):
        response = client.post(
            f"/api/v1/scan-sessions/{session_id}/capture", files=files
        )
        assert response.status_code == 200
        data = response.json()

        assert data["detected"] is False
        assert data["candidates"] == []
        assert data["best_match"] is None
        assert data["scan"]["crop_status"] == "none"


def test_api_capture_frame_closed_session(client: TestClient):
    """POST /api/v1/scan-sessions/{id}/capture returns 409 if session is completed."""
    create_resp = client.post("/api/v1/scan-sessions")
    session_id = create_resp.json()["id"]

    client.post(f"/api/v1/scan-sessions/{session_id}/complete")

    image_bytes = _create_test_image()
    files = {"file": ("frame.jpg", image_bytes, "image/jpeg")}

    response = client.post(f"/api/v1/scan-sessions/{session_id}/capture", files=files)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "SESSION_NOT_ACTIVE"


def test_api_capture_frame_multiple_files_rejected(client: TestClient):
    """POST /api/v1/scan-sessions/{id}/capture rejects multiple files with 422."""
    create_resp = client.post("/api/v1/scan-sessions")
    session_id = create_resp.json()["id"]

    files = [
        ("file", ("frame1.jpg", _create_test_image(), "image/jpeg")),
        ("file", ("frame2.jpg", _create_test_image(), "image/jpeg")),
    ]
    response = client.post(f"/api/v1/scan-sessions/{session_id}/capture", files=files)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MULTIPLE_FILES"


def test_api_capture_frame_empty_file_rejected(client: TestClient):
    """POST /api/v1/scan-sessions/{id}/capture rejects empty file with 422."""
    create_resp = client.post("/api/v1/scan-sessions")
    session_id = create_resp.json()["id"]

    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    response = client.post(f"/api/v1/scan-sessions/{session_id}/capture", files=files)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "EMPTY_FILE"
