import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scan import Scan


def _create_jpeg_bytes(size: tuple[int, int] = (100, 150)) -> bytes:
    buf = io.BytesIO()
    im = Image.new("RGB", size, color="blue")
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_upload_success(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))

    payload = _create_jpeg_bytes((120, 160))
    files = {"file": ("card.jpg", payload, "image/jpeg")}

    response = client.post("/api/v1/scans", files=files)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["status"] == "uploaded"
    assert data["width"] == 120
    assert data["height"] == 160
    assert data["content_type"] == "image/jpeg"
    assert data["file_size"] > 0
    assert data["image_url"] == f"/api/v1/scans/{data['id']}/image"

    stored_file = tmp_path / "uploads" / f"{data['id']}.jpg"
    assert stored_file.exists()
    assert stored_file.stat().st_size == data["file_size"]


def test_multiple_files_rejected(client: TestClient, db: Session) -> None:
    response = client.post(
        "/api/v1/scans",
        files=[
            ("file", ("a.jpg", _create_jpeg_bytes(), "image/jpeg")),
            ("file", ("b.jpg", _create_jpeg_bytes(), "image/jpeg")),
        ],
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "MULTIPLE_FILES"
    assert db.query(Scan).count() == 0


def test_disk_full_returns_storage_error(
    client: TestClient,
    db: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    payload = _create_jpeg_bytes()
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path))

    def failing_save(*args, **kwargs):
        raise OSError("Disk full")

    monkeypatch.setattr(Image.Image, "save", failing_save)
    response = client.post(
        "/api/v1/scans", files={"file": ("a.jpg", payload, "image/jpeg")}
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "STORAGE_ERROR"
    assert db.query(Scan).count() == 0
    assert not list(tmp_path.glob("*.jpg"))
    assert not list((tmp_path / ".tmp").iterdir())


def test_upload_does_not_require_post_commit_refresh(
    client: TestClient,
    db: Session,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path))

    def fail_refresh(*args, **kwargs):
        raise RuntimeError("Read connection unavailable after commit")

    monkeypatch.setattr(db, "refresh", fail_refresh)
    response = client.post(
        "/api/v1/scans",
        files={"file": ("card.jpg", _create_jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 201
    assert (tmp_path / f"{response.json()['id']}.jpg").is_file()
    assert db.query(Scan).count() == 1


def test_get_scan_metadata_and_image(
    client: TestClient, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))

    payload = _create_jpeg_bytes((100, 100))
    res = client.post(
        "/api/v1/scans", files={"file": ("card.jpg", payload, "image/jpeg")}
    )
    assert res.status_code == 201
    scan_id = res.json()["id"]

    # 1. GET metadata
    meta_res = client.get(f"/api/v1/scans/{scan_id}")
    assert meta_res.status_code == 200
    meta = meta_res.json()
    assert meta["id"] == scan_id
    assert meta["width"] == 100
    assert meta["height"] == 100

    # 2. GET image
    img_res = client.get(f"/api/v1/scans/{scan_id}/image")
    assert img_res.status_code == 200
    assert img_res.headers["content-type"] == "image/jpeg"
    assert img_res.headers.get("cache-control") == "no-store"

    # Decode returned image
    with Image.open(io.BytesIO(img_res.content)) as im:
        assert im.format == "JPEG"
        assert im.size == (100, 100)


def test_get_unknown_or_invalid_scan_404(client: TestClient) -> None:
    # Random unknown UUID
    res = client.get(f"/api/v1/scans/{uuid.uuid4()}")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "SCAN_NOT_FOUND"

    # Invalid non-UUID format
    res_invalid = client.get("/api/v1/scans/not-a-valid-uuid")
    assert res_invalid.status_code == 404
    assert res_invalid.json()["detail"]["code"] == "SCAN_NOT_FOUND"


def test_get_expired_scan_404(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    scan_id = str(uuid.uuid4())
    img_file = upload_dir / f"{scan_id}.jpg"
    img_file.write_bytes(_create_jpeg_bytes())

    # Create expired scan in DB
    past_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=2)
    scan = Scan(
        id=scan_id,
        status="uploaded",
        image_path=f"{scan_id}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=img_file.stat().st_size,
        created_at=past_time - timedelta(hours=24),
        expires_at=past_time,
    )
    db.add(scan)
    db.commit()

    # Metadata request returns 404
    res_meta = client.get(f"/api/v1/scans/{scan_id}")
    assert res_meta.status_code == 404
    assert res_meta.json()["detail"]["code"] == "SCAN_EXPIRED"

    # Image request returns 404
    res_img = client.get(f"/api/v1/scans/{scan_id}/image")
    assert res_img.status_code == 404
    assert res_img.json()["detail"]["code"] == "SCAN_EXPIRED"


def test_missing_stored_file_returns_404(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))
    scan_id = str(uuid.uuid4())
    now_utc = datetime.now(UTC).replace(tzinfo=None)

    scan = Scan(
        id=scan_id,
        status="uploaded",
        image_path=f"{scan_id}.jpg",  # file not created on disk
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=500,
        created_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
    )
    db.add(scan)
    db.commit()

    res = client.get(f"/api/v1/scans/{scan_id}")
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "IMAGE_NOT_FOUND"


def test_file_write_failure_leaves_no_committed_scan(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))

    # Force processing failure
    def failing_processor(*args, **kwargs):
        raise OSError("Disk write failed simulated")

    monkeypatch.setattr(
        "app.api.v1.scans.process_and_normalize_image",
        failing_processor,
    )

    payload = _create_jpeg_bytes()
    response = client.post(
        "/api/v1/scans", files={"file": ("card.jpg", payload, "image/jpeg")}
    )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "STORAGE_ERROR"
    assert not list((tmp_path / "uploads" / ".tmp").iterdir())

    assert db.query(Scan).count() == 0


def test_database_failure_cleans_up_new_file(
    client: TestClient, db: Session, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_DIRECTORY", str(tmp_path / "uploads"))

    # Force database commit failure
    def failing_commit():
        raise RuntimeError("Simulated DB failure")

    monkeypatch.setattr(db, "commit", failing_commit)

    payload = _create_jpeg_bytes()
    res = client.post(
        "/api/v1/scans", files={"file": ("card.jpg", payload, "image/jpeg")}
    )
    assert res.status_code == 500
    assert res.json()["detail"]["code"] == "DATABASE_ERROR"

    # Verify no file remained in storage
    files = list((tmp_path / "uploads").glob("*.jpg"))
    assert len(files) == 0


def test_oversized_body_with_content_length_413(
    client: TestClient, monkeypatch
) -> None:
    # Lower max limit to 1000 bytes
    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 1000)
    monkeypatch.setattr(settings, "UPLOAD_REQUEST_OVERHEAD_BYTES", 100)

    # Payload larger than 1100 bytes
    big_payload = b"X" * 1500
    res = client.post(
        "/api/v1/scans",
        files={"file": ("card.jpg", big_payload, "image/jpeg")},
        headers={"Origin": settings.CORS_ORIGINS[0]},
    )
    assert res.status_code == 413
    assert res.headers["access-control-allow-origin"] == settings.CORS_ORIGINS[0]
    assert res.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"


def test_oversized_chunked_body_without_content_length_413(
    client: TestClient, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "UPLOAD_MAX_BYTES", 500)
    monkeypatch.setattr(settings, "UPLOAD_REQUEST_OVERHEAD_BYTES", 50)

    boundary = "----TestBoundary123"
    content_type = f"multipart/form-data; boundary={boundary}"

    def chunk_generator():
        yield (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="card.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode()
        for _ in range(10):
            yield b"A" * 100
        yield f"\r\n--{boundary}--\r\n".encode()

    res = client.post(
        "/api/v1/scans",
        content=chunk_generator(),
        headers={"content-type": content_type},
    )
    assert res.status_code == 413
    assert res.json()["detail"]["code"] == "PAYLOAD_TOO_LARGE"
