import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.commands.cleanup_scans import cleanup_expired_scans, cleanup_orphan_files
from app.models.scan import Scan


def test_orphan_cleanup_preserves_recent_referenced_and_unrelated_files(
    db: Session,
    tmp_path: Path,
) -> None:
    old = (datetime.now(UTC) - timedelta(hours=49)).timestamp()
    abandoned = tmp_path / f"{uuid.uuid4()}.jpg"
    recent = tmp_path / f"{uuid.uuid4()}.jpg"
    unrelated = tmp_path / "photo.jpg"
    temp_dir = tmp_path / ".tmp"
    temp_dir.mkdir()
    interrupted = temp_dir / f"upload_{uuid.uuid4().hex}.tmp"
    scan_id = str(uuid.uuid4())
    referenced = tmp_path / f"{scan_id}.jpg"
    for path in (abandoned, unrelated, interrupted, referenced):
        path.write_bytes(b"test")
        os.utime(path, (old, old))
    recent.write_bytes(b"recent")
    now = datetime.now(UTC).replace(tzinfo=None)
    db.add(
        Scan(
            id=scan_id,
            status="uploaded",
            image_path=referenced.name,
            content_type="image/jpeg",
            width=1,
            height=1,
            file_size=4,
            created_at=now,
            expires_at=now + timedelta(hours=24),
        )
    )
    db.commit()
    assert cleanup_orphan_files(db, tmp_path) == (2, 0)
    assert not abandoned.exists()
    assert not interrupted.exists()
    assert recent.exists() and unrelated.exists() and referenced.exists()


def test_cleanup_expired_and_non_expired_scans(db: Session, tmp_path: Path) -> None:
    storage_root = tmp_path / "uploads"
    storage_root.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(UTC).replace(tzinfo=None)

    # 1. Expired scan with file
    id_exp = str(uuid.uuid4())
    file_exp = storage_root / f"{id_exp}.jpg"
    file_exp.write_bytes(b"JPEG-EXPIRED")

    scan_exp = Scan(
        id=id_exp,
        status="uploaded",
        image_path=f"{id_exp}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=len(b"JPEG-EXPIRED"),
        created_at=now_utc - timedelta(hours=48),
        expires_at=now_utc - timedelta(hours=24),
    )
    db.add(scan_exp)

    # 2. Non-expired scan with file
    id_valid = str(uuid.uuid4())
    file_valid = storage_root / f"{id_valid}.jpg"
    file_valid.write_bytes(b"JPEG-VALID")

    scan_valid = Scan(
        id=id_valid,
        status="uploaded",
        image_path=f"{id_valid}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=len(b"JPEG-VALID"),
        created_at=now_utc,
        expires_at=now_utc + timedelta(hours=24),
    )
    db.add(scan_valid)

    # 3. Unrelated file that should remain untouched
    unrelated_file = storage_root / "unrelated.txt"
    unrelated_file.write_text("Do not touch")

    db.commit()

    # Run cleanup
    deleted_records, deleted_files, missing_files, failed_files = cleanup_expired_scans(
        db=db,
        storage_root=storage_root,
    )

    assert deleted_records == 1
    assert deleted_files == 1
    assert missing_files == 0
    assert failed_files == 0

    # Verify expired scan and file are gone
    assert not file_exp.exists()
    assert db.query(Scan).filter(Scan.id == id_exp).first() is None

    # Verify non-expired scan and file remain
    assert file_valid.exists()
    assert db.query(Scan).filter(Scan.id == id_valid).first() is not None

    # Verify unrelated file was preserved
    assert unrelated_file.exists()
    assert unrelated_file.read_text() == "Do not touch"


def test_cleanup_handles_already_missing_file(db: Session, tmp_path: Path) -> None:
    storage_root = tmp_path / "uploads"
    storage_root.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    id_missing = str(uuid.uuid4())

    scan = Scan(
        id=id_missing,
        status="uploaded",
        image_path=f"{id_missing}.jpg",  # No file on disk
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=123,
        created_at=now_utc - timedelta(hours=48),
        expires_at=now_utc - timedelta(hours=24),
    )
    db.add(scan)
    db.commit()

    deleted_records, deleted_files, missing_files, failed_files = cleanup_expired_scans(
        db=db,
        storage_root=storage_root,
    )

    assert deleted_records == 1
    assert deleted_files == 0
    assert missing_files == 1
    assert failed_files == 0
    assert db.query(Scan).filter(Scan.id == id_missing).first() is None


def test_cleanup_file_deletion_failure_keeps_record_for_retry(
    db: Session, tmp_path: Path, monkeypatch
) -> None:
    storage_root = tmp_path / "uploads"
    storage_root.mkdir(parents=True, exist_ok=True)

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    id_locked = str(uuid.uuid4())
    file_locked = storage_root / f"{id_locked}.jpg"
    file_locked.write_bytes(b"LOCKED-FILE")

    scan = Scan(
        id=id_locked,
        status="uploaded",
        image_path=f"{id_locked}.jpg",
        content_type="image/jpeg",
        width=100,
        height=100,
        file_size=len(b"LOCKED-FILE"),
        created_at=now_utc - timedelta(hours=48),
        expires_at=now_utc - timedelta(hours=24),
    )
    db.add(scan)
    db.commit()

    # Simulate permission/OS failure on file deletion
    def failing_remove(path):
        raise PermissionError("Access is denied")

    monkeypatch.setattr(os, "remove", failing_remove)

    deleted_records, deleted_files, missing_files, failed_files = cleanup_expired_scans(
        db=db,
        storage_root=storage_root,
    )

    assert deleted_records == 0
    assert deleted_files == 0
    assert missing_files == 0
    assert failed_files == 1

    # Database record is preserved so retry can succeed
    retained_scan = db.query(Scan).filter(Scan.id == id_locked).first()
    assert retained_scan is not None
    assert file_locked.exists()
