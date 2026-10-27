import logging
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.scan import Scan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cleanup_scans")


def cleanup_expired_scans(
    db: Session,
    batch_size: int = 100,
    storage_root: Path | None = None,
) -> tuple[int, int, int, int]:
    """Find expired scans in bounded batches, remove files, and delete records.

    If file deletion fails (e.g. file lock or permission error), the database record
    is preserved so that future runs can retry cleanup without losing tracking.

    Returns:
        tuple of (deleted_records, deleted_files, missing_files, failed_files)
    """
    if storage_root is None:
        storage_root = Path(settings.UPLOAD_DIRECTORY)
    storage_root = storage_root.resolve()
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    total_deleted_records = 0
    total_deleted_files = 0
    total_missing_files = 0
    total_failed_files = 0

    failed_scan_ids: set[str] = set()

    logger.info("Starting expired scan cleanup cutoff at UTC %s", now_utc)

    while True:
        query = (
            db.query(Scan)
            .filter(Scan.expires_at <= now_utc)
            .order_by(Scan.expires_at.asc())
        )
        if failed_scan_ids:
            query = query.filter(~Scan.id.in_(failed_scan_ids))

        batch = query.limit(batch_size).all()
        if not batch:
            break

        records_to_delete: list[Scan] = []

        for scan in batch:
            files_to_check = [scan.image_path]
            if scan.crop_path:
                files_to_check.append(scan.crop_path)

            all_files_ok = True
            for rel_path in files_to_check:
                file_path = (storage_root / rel_path).resolve()

                # Security check: verify path is inside configured upload root
                if not file_path.is_relative_to(storage_root):
                    logger.error(
                        "Path traversal hazard detected for scan %s path %s; skipping.",
                        scan.id,
                        rel_path,
                    )
                    all_files_ok = False
                    total_failed_files += 1
                    break

                try:
                    if file_path.exists():
                        os.remove(file_path)
                        total_deleted_files += 1
                        logger.debug("Deleted scan file: %s", file_path)
                    else:
                        total_missing_files += 1
                        logger.warning(
                            "Scan file already missing for scan %s at %s",
                            scan.id,
                            file_path,
                        )
                except OSError as exc:
                    logger.error(
                        "Failed to delete scan file %s for scan %s: %s",
                        file_path,
                        scan.id,
                        exc,
                    )
                    all_files_ok = False
                    total_failed_files += 1

            if not all_files_ok:
                failed_scan_ids.add(scan.id)
            else:
                records_to_delete.append(scan)

        for scan in records_to_delete:
            db.delete(scan)

        if records_to_delete:
            db.commit()
            total_deleted_records += len(records_to_delete)
            logger.info(
                "Committed batch of %d deleted scan records",
                len(records_to_delete),
            )

    logger.info(
        "Cleanup finished: %d records deleted "
        "(%d files removed, %d missing, %d failed)",
        total_deleted_records,
        total_deleted_files,
        total_missing_files,
        total_failed_files,
    )

    return (
        total_deleted_records,
        total_deleted_files,
        total_missing_files,
        total_failed_files,
    )


def cleanup_orphan_files(
    db: Session, storage_root: Path | None = None
) -> tuple[int, int]:
    """Remove only old, app-generated files with no database reference.

    A minimum 24-hour grace period protects uploads and crops still being committed.
    Symlinks, nested directories and unrelated filenames are never followed.
    """
    root = (storage_root or Path(settings.UPLOAD_DIRECTORY)).resolve()
    cutoff = time.time() - max(24, settings.UPLOAD_RETENTION_HOURS) * 3600
    removed = failed = 0
    uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    for directory, pattern in (
        (
            root,
            rf"{uuid_pattern}(?:_crop(?:_[0-9a-f]{{32}})?)?\.(?:jpg|tmp_[0-9a-f]{{32}})",
        ),
        (root / ".tmp", r"upload_[0-9a-f]{32}\.tmp"),
    ):
        if directory.is_symlink() or not directory.is_dir():
            continue
        for path in directory.iterdir():
            if not re.fullmatch(pattern, path.name) or path.is_symlink():
                continue
            try:
                if not path.is_file() or path.stat().st_mtime >= cutoff:
                    continue
                relative = path.relative_to(root).as_posix()
                if (
                    db.query(Scan.id)
                    .filter(
                        or_(
                            Scan.image_path == relative,
                            Scan.crop_path == relative,
                        )
                    )
                    .first()
                ):
                    continue
                path.unlink()
                removed += 1
            except OSError:
                logger.exception("Cannot remove orphan file %s", path)
                failed += 1
    logger.info("Orphan cleanup: %d removed, %d failed", removed, failed)
    return removed, failed


def main() -> int:
    db = SessionLocal()
    try:
        _, _, _, failed = cleanup_expired_scans(db)
        _, orphan_failed = cleanup_orphan_files(db)
        return 1 if failed + orphan_failed > 0 else 0
    finally:
        db.close()


if __name__ == "__main__":
    if "--loop" in sys.argv:
        while True:
            try:
                main()
            except Exception:
                logger.exception("Cleanup failed; retrying on next hourly run")
            time.sleep(3600)
    sys.exit(main())
