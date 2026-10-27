import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import text

from app.api.v1.cards import get_tcgdex_client
from app.main import app
from app.services.ocr.engine import (
    OcrResult,
    OcrTimeoutError,
    OcrUnavailableError,
)


def test_saved_evidence_survives_reload(db):
    from app.api.v1.scans import _build_scan_response
    from app.models.scan import Scan

    scan = Scan(
        id="evidence-regression",
        image_path="test.jpg",
        width=281,
        height=393,
        file_size=100,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        recognized_name="Steelix",
        recognized_number="8",
        recognition_evidence={
            "name": {
                "raw_text": "Steelix",
                "normalized": "Steelix",
                "confidence_level": "low",
                "source_region": "header",
                "alternatives": ["Steelix"],
            },
            "number": {
                "raw_text": "8",
                "normalized": "8",
                "confidence_level": "low",
                "source_region": "bottom_right",
                "alternatives": ["8"],
            },
            "denominator": {"confidence_level": "low"},
            "set_info": {"confidence_level": "low"},
            "image_quality": {"width": 281, "height": 393, "is_low_res": True},
        },
    )
    db.add(scan)
    db.commit()
    db.expire_all()
    loaded = db.get(Scan, scan.id)
    response = _build_scan_response(loaded)
    assert response.evidence.number.confidence_level == "low"
    assert response.evidence.number.source_region == "bottom_right"
    assert response.evidence.name.alternatives == ["Steelix"]


def _create_test_card_image(name: str = "Pikachu", number: str = "058/102") -> bytes:
    """Generate a clean synthetic Pokémon card image with header and footer text."""
    # 600x840 px (aspect ratio ~0.714)
    img = Image.new("RGB", (600, 840), color=(240, 230, 160))
    draw = ImageDraw.Draw(img)

    # Header region (name on top-left)
    draw.rectangle([20, 20, 580, 120], fill=(255, 255, 255), outline=(0, 0, 0), width=2)
    draw.text((40, 50), f"{name} HP 60", fill=(0, 0, 0))

    # Center card art placeholder
    draw.rectangle(
        [40, 140, 560, 500], fill=(180, 200, 240), outline=(0, 0, 0), width=2
    )

    # Footer region (number on bottom-left)
    draw.rectangle(
        [20, 720, 580, 820], fill=(255, 255, 255), outline=(0, 0, 0), width=2
    )
    draw.text((40, 760), f"MEW {number} (c)2023 Pokemon", fill=(0, 0, 0))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture
def mock_tcgdex_client():
    mock = AsyncMock()
    # Mock search response
    mock.get_cards_search.return_value = [
        {
            "id": "base1-58",
            "name": "Pikachu",
            "localId": "58",
            "set": {"id": "base1", "name": "Base Set"},
            "image": "https://assets.tcgdex.net/en/base/base1/58",
        },
        {
            "id": "sv3pt5-25",
            "name": "Pikachu",
            "localId": "025",
            "set": {"id": "sv3pt5", "name": "151"},
            "image": "https://assets.tcgdex.net/en/sv/sv3pt5/025",
        },
    ]
    # Mock individual card response
    mock.get_card.return_value = {
        "id": "base1-58",
        "name": "Pikachu",
        "localId": "58",
        "set": {"id": "base1", "name": "Base Set"},
        "image": "https://assets.tcgdex.net/en/base/base1/58",
    }
    return mock


@pytest.fixture
def client_with_mock_catalog(mock_tcgdex_client):
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_tcgdex_client
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_tcgdex_client, None)


def _upload_and_confirm_card_crop(client: TestClient) -> dict:
    """Helper to upload a card image, crop it, and confirm the crop."""
    img_bytes = _create_test_card_image("Pikachu", "058/102")
    files = {"file": ("card.jpg", img_bytes, "image/jpeg")}
    upload_res = client.post("/api/v1/scans", files=files)
    assert upload_res.status_code == 201
    scan_id = upload_res.json()["id"]

    # Crop
    crop_payload = {
        "corners": {
            "top_left": {"x": 0.05, "y": 0.05},
            "top_right": {"x": 0.95, "y": 0.05},
            "bottom_right": {"x": 0.95, "y": 0.95},
            "bottom_left": {"x": 0.05, "y": 0.95},
        },
        "rotation": 0,
        "expected_version": 0,
    }
    crop_res = client.post(f"/api/v1/scans/{scan_id}/crop", json=crop_payload)
    assert crop_res.status_code == 200
    crop_version = crop_res.json()["crop_version"]

    # Confirm crop
    confirm_res = client.post(
        f"/api/v1/scans/{scan_id}/confirm",
        json={"crop_version": crop_version},
    )
    assert confirm_res.status_code == 200
    return confirm_res.json()


def test_recognize_requires_confirmed_crop(client_with_mock_catalog):
    # Upload scan without confirming crop
    img_bytes = _create_test_card_image()
    files = {"file": ("card.jpg", img_bytes, "image/jpeg")}
    upload_res = client_with_mock_catalog.post("/api/v1/scans", files=files)
    scan_id = upload_res.json()["id"]

    res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "CROP_NOT_CONFIRMED"


def test_recognize_success_and_persistence(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]

    # Mock OCR engine to return deterministic text for test
    mock_ocr = MagicMock()
    mock_ocr.recognize.side_effect = [
        OcrResult(raw_text="Pikachu HP 60", confidence=95.0),  # Header
        OcrResult(raw_text="MEW 058/102 (c)2023", confidence=90.0),  # Footer
        OcrResult(raw_text="058/102", confidence=90.0),  # Footer validation
        OcrResult(raw_text="058/102", confidence=90.0),  # Inverted footer
        OcrResult(raw_text="Gnaw 20\nThunder Jolt 30", confidence=90.0),  # Body
        OcrResult(raw_text="HP 60", confidence=95.0),  # HP
    ] + [OcrResult(raw_text="", confidence=50.0)] * 10

    with patch("app.api.v1.scans.get_ocr_engine", return_value=mock_ocr):
        rec_res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
        assert rec_res.status_code == 200
        data = rec_res.json()

        assert data["recognized_name"] == "Pikachu"
        assert data["recognized_number"] == "058/102"
        assert data["recognized_set_code"] == "MEW"
        assert data["evidence"]["hp"] == "60"
        assert data["evidence"]["attacks"] == ["Gnaw", "Thunder Jolt"]
        assert len(data["candidates"]) > 0
        assert data["candidates"][0]["id"] == "base1-58"
        assert "hp" in data["candidates"][0]
        assert "matched_attacks" in data["candidates"][0]
        assert "matched_abilities" in data["candidates"][0]
        assert "visual_similarity" in data["candidates"][0]

    # Reload scan via GET /api/v1/scans/{id} and verify recognition state persisted
    get_res = client_with_mock_catalog.get(f"/api/v1/scans/{scan_id}")
    assert get_res.status_code == 200
    scan_persisted = get_res.json()
    assert scan_persisted["recognition_status"] == "completed"
    assert scan_persisted["recognized_name"] == "Pikachu"
    assert scan_persisted["recognized_number"] == "058/102"
    assert scan_persisted["evidence"]["hp"] == "60"
    assert scan_persisted["evidence"]["attacks"] == ["Gnaw", "Thunder Jolt"]
    assert len(scan_persisted["candidates"]) > 0
    assert "hp" in scan_persisted["candidates"][0]
    assert "matched_attacks" in scan_persisted["candidates"][0]
    assert "matched_abilities" in scan_persisted["candidates"][0]
    assert "visual_similarity" in scan_persisted["candidates"][0]


def test_search_candidates_flow(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    search_payload = {
        "name": "Pikachu",
        "number": "58/102",
        "expected_crop_version": crop_ver,
    }
    res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/search-candidates",
        json=search_payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["search_version"] >= 1
    assert len(data["candidates"]) > 0


def test_confirm_catalog_card_success_and_persistence(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    confirm_payload = {
        "card_id": "base1-58",
        "expected_crop_version": crop_ver,
    }
    res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json=confirm_payload,
    )
    assert res.status_code == 200
    card_info = res.json()["confirmed_card"]
    assert card_info is not None
    assert card_info["id"] == "base1-58"
    assert card_info["name"] == "Pikachu"
    assert card_info["set_name"] == "Base Set"
    assert card_info["number"] == "58"
    assert card_info["confirmed_at"] is not None

    # Verify survival across browser reload (GET)
    get_res = client_with_mock_catalog.get(f"/api/v1/scans/{scan_id}")
    assert get_res.status_code == 200
    assert get_res.json()["confirmed_card"]["id"] == "base1-58"


def test_reset_card_confirmation(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    # First confirm a card
    client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json={"card_id": "base1-58", "expected_crop_version": crop_ver},
    )

    # Reset card confirmation
    reset_res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/reset-card-confirmation",
        json={"expected_crop_version": crop_ver},
    )
    assert reset_res.status_code == 200
    assert reset_res.json()["confirmed_card"] is None

    # Check GET
    get_res = client_with_mock_catalog.get(f"/api/v1/scans/{scan_id}")
    assert get_res.json()["confirmed_card"] is None
    # Crop remains intact
    assert get_res.json()["crop_status"] == "confirmed"


def test_stale_crop_version_protection(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    stale_crop_ver = scan_data["crop_version"] - 1

    confirm_payload = {
        "card_id": "base1-58",
        "expected_crop_version": stale_crop_ver,
    }
    res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json=confirm_payload,
    )
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "STALE_VERSION"


def test_crop_replacement_invalidates_recognition_and_confirmation(
    client_with_mock_catalog,
):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    # Confirm card
    client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json={"card_id": "base1-58", "expected_crop_version": crop_ver},
    )

    # Replace crop with new coordinates
    new_crop_payload = {
        "corners": {
            "top_left": {"x": 0.1, "y": 0.1},
            "top_right": {"x": 0.9, "y": 0.1},
            "bottom_right": {"x": 0.9, "y": 0.9},
            "bottom_left": {"x": 0.1, "y": 0.9},
        },
        "rotation": 90,
        "expected_version": crop_ver,
    }
    crop_res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/crop",
        json=new_crop_payload,
    )
    assert crop_res.status_code == 200
    data = crop_res.json()
    assert data["crop_status"] == "preview"
    assert data["confirmed_card"] is None
    assert data["recognition_status"] == "none"


def test_expired_scan_cannot_recognize_or_confirm(client_with_mock_catalog, db):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    # Artificially expire scan in database
    past = datetime.now(UTC) - timedelta(hours=2)
    db.execute(
        text("UPDATE scans SET expires_at = :past WHERE id = :id"),
        {"past": past.replace(tzinfo=None), "id": scan_id},
    )
    db.commit()

    # Attempt recognize on expired scan
    rec_res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
    assert rec_res.status_code == 404
    assert rec_res.json()["detail"]["code"] == "SCAN_EXPIRED"

    # Attempt confirm on expired scan
    conf_res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/confirm-card",
        json={"card_id": "base1-58", "expected_crop_version": crop_ver},
    )
    assert conf_res.status_code == 404
    assert conf_res.json()["detail"]["code"] == "SCAN_EXPIRED"


def test_ocr_unavailable_error_handling(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]

    mock_engine = MagicMock()
    mock_engine.recognize.side_effect = OcrUnavailableError("Tesseract not found")

    with patch("app.api.v1.scans.get_ocr_engine", return_value=mock_engine):
        res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
        assert res.status_code == 503
        assert res.json()["detail"]["code"] == "OCR_UNAVAILABLE"


def test_ocr_timeout_error_handling(client_with_mock_catalog):
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]

    mock_engine = MagicMock()
    mock_engine.recognize.side_effect = OcrTimeoutError("OCR execution timed out")

    with patch("app.api.v1.scans.get_ocr_engine", return_value=mock_engine):
        res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
        assert res.status_code == 504
        assert res.json()["detail"]["code"] == "OCR_TIMEOUT"


def test_catalog_unavailable_during_recognition_preserves_ocr(
    client_with_mock_catalog,
):
    """When catalog provider is unavailable, OCR text must be preserved

    and catalog_status must be 'unavailable' rather than empty matches.
    """
    from app.services.catalog import CatalogUnavailableError

    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]

    mock_client = AsyncMock()
    mock_client.get_cards_search.side_effect = CatalogUnavailableError(
        "503 Service Unavailable"
    )
    app.dependency_overrides[get_tcgdex_client] = lambda: mock_client

    mock_ocr = MagicMock()
    mock_ocr.recognize.return_value = OcrResult(
        raw_text="Pikachu HP 60\n058/102", confidence=90.0
    )

    with patch("app.api.v1.scans.get_ocr_engine", return_value=mock_ocr):
        rec_res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
    assert rec_res.status_code == 200
    data = rec_res.json()

    assert data["catalog_status"] == "unavailable"
    assert data["candidates"] == []
    assert data["recognized_name"] is not None
    assert data["raw_text"] is not None

    # Verify persisted in database across reload
    get_res = client_with_mock_catalog.get(f"/api/v1/scans/{scan_id}")
    assert get_res.status_code == 200
    scan_json = get_res.json()
    assert scan_json["catalog_status"] == "unavailable"
    assert scan_json["recognized_name"] == data["recognized_name"]
    assert scan_json["ocr_raw_text"] == data["raw_text"]
    app.dependency_overrides.pop(get_tcgdex_client, None)


def test_user_search_fields_persistence(client_with_mock_catalog):
    """User-edited search fields must persist in DB and return on reload."""
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    search_res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/search-candidates",
        json={
            "name": "Mewtwo",
            "number": "10/102",
            "set_code": "BS",
            "expected_crop_version": crop_ver,
            "expected_search_version": 0,
        },
    )
    assert search_res.status_code == 200
    assert search_res.json()["search_version"] == 1

    # Reload scan
    get_res = client_with_mock_catalog.get(f"/api/v1/scans/{scan_id}")
    assert get_res.status_code == 200
    scan_json = get_res.json()
    assert scan_json["user_search_name"] == "Mewtwo"
    assert scan_json["user_search_number"] == "10/102"
    assert scan_json["user_search_set_code"] == "BS"
    assert scan_json["search_version"] == 1


def test_rerunning_recognition_preserves_user_manual_search(client_with_mock_catalog):
    """Re-running OCR updates recognition values but preserves manual search values."""
    scan_data = _upload_and_confirm_card_crop(client_with_mock_catalog)
    scan_id = scan_data["id"]
    crop_ver = scan_data["crop_version"]

    # 1. User performs manual search
    search_res = client_with_mock_catalog.post(
        f"/api/v1/scans/{scan_id}/search-candidates",
        json={
            "name": "Custom Pikachu",
            "number": "99/100",
            "set_code": "CUSTOM",
            "expected_crop_version": crop_ver,
            "expected_search_version": 0,
        },
    )
    assert search_res.status_code == 200
    curr_search_ver = search_res.json()["search_version"]

    # 2. Re-run recognition
    mock_ocr = MagicMock()
    mock_ocr.recognize.side_effect = [
        OcrResult(raw_text="Raichu HP 90", confidence=96.0),  # Header
        OcrResult(raw_text="MEW 014/102 (c)2023", confidence=92.0),  # Footer
        OcrResult(raw_text="014/102", confidence=90.0),  # Footer validation
        OcrResult(raw_text="014/102", confidence=90.0),  # Inverted footer
        OcrResult(raw_text="Thunderbolt 100", confidence=91.0),  # Body
        OcrResult(raw_text="HP 90", confidence=96.0),  # HP
    ] + [OcrResult(raw_text="", confidence=50.0)] * 10

    with patch("app.api.v1.scans.get_ocr_engine", return_value=mock_ocr):
        rec_res = client_with_mock_catalog.post(f"/api/v1/scans/{scan_id}/recognize")
        assert rec_res.status_code == 200
        rec_data = rec_res.json()
        assert rec_data["recognized_name"] == "Raichu"
        assert rec_data["recognized_number"] == "014/102"
        assert rec_data["recognized_set_code"] == "MEW"
        assert rec_data["evidence"]["hp"] == "90"
        assert rec_data["evidence"]["attacks"] == ["Thunderbolt"]

    # 3. Verify GET /api/v1/scans/{id}: OCR updated, manual search preserved!
    get_res = client_with_mock_catalog.get(f"/api/v1/scans/{scan_id}")
    assert get_res.status_code == 200
    scan_json = get_res.json()
    # Updated OCR fields
    assert scan_json["recognized_name"] == "Raichu"
    assert scan_json["recognized_number"] == "014/102"
    assert scan_json["recognized_set_code"] == "MEW"
    assert scan_json["evidence"]["hp"] == "90"
    assert scan_json["evidence"]["attacks"] == ["Thunderbolt"]
    # Preserved user manual search fields
    assert scan_json["user_search_name"] == "Custom Pikachu"
    assert scan_json["user_search_number"] == "99/100"
    assert scan_json["user_search_set_code"] == "CUSTOM"
    assert scan_json["search_version"] == curr_search_ver + 1


def test_candidate_new_fields_and_evidence_persistence(db):
    """Test serialization and deserialization of candidate items and evidence."""
    from app.api.v1.scans import _build_scan_response
    from app.models.scan import Scan

    scan = Scan(
        id="candidate-enrichment-test",
        image_path="test_enrich.jpg",
        width=400,
        height=600,
        file_size=5000,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        crop_width=400,
        crop_height=600,
        crop_status="confirmed",
        recognized_name="Gengar",
        recognized_number="094/165",
        recognition_evidence={
            "name": {
                "raw_text": "Gengar",
                "normalized": "Gengar",
                "confidence_level": "high",
            },
            "number": {
                "raw_text": "094/165",
                "normalized": "094/165",
                "confidence_level": "high",
            },
            "denominator": {"confidence_level": "high"},
            "set_info": {"confidence_level": "high"},
            "image_quality": {"width": 400, "height": 600, "is_low_res": False},
            "hp": "130",
            "attacks": ["Shadow Ball", "Night Shade"],
            "abilities": ["Cursed Body"],
        },
        candidate_matches=[
            {
                "id": "me-94",
                "name": "Gengar",
                "local_id": "094",
                "set_id": "me",
                "set_name": "Pokemon 151",
                "image_url": "https://assets.tcgdex.net/en/me/me/094/low.webp",
                "score": 95,
                "reasons": ["Collector number match", "Card name match"],
                "hp": "130",
                "matched_attacks": ["Shadow Ball"],
                "matched_abilities": ["Cursed Body"],
                "visual_similarity": 0.92,
            }
        ],
    )
    db.add(scan)
    db.commit()
    db.expire_all()

    loaded = db.get(Scan, scan.id)
    resp = _build_scan_response(loaded)

    assert resp.evidence is not None
    assert resp.evidence.hp == "130"
    assert resp.evidence.attacks == ["Shadow Ball", "Night Shade"]
    assert resp.evidence.abilities == ["Cursed Body"]

    assert resp.candidates is not None
    assert len(resp.candidates) == 1
    cand = resp.candidates[0]
    assert cand.hp == "130"
    assert cand.matched_attacks == ["Shadow Ball"]
    assert cand.matched_abilities == ["Cursed Body"]
    assert cand.visual_similarity == 0.92
