import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.api.v1.scans import build_scan_response, serialize_candidate
from app.core.config import settings
from app.core.database import get_db
from app.models.collection import CollectionItem, CollectionScanLink
from app.models.scan import Scan
from app.models.scan_session import ScanSession
from app.schemas.scan import (
    CandidateMatchItem,
    ConfirmedCardInfo,
)
from app.schemas.scan_session import (
    LiveCaptureResponse,
    ScanSessionDetailResponse,
    ScanSessionItemResponse,
    ScanSessionResponse,
)
from app.services.card_catalog import (
    CardCatalogService,
    get_card_catalog_service,
)
from app.services.card_detector import detect_card_corners
from app.services.catalog import (
    CatalogUnavailableError,
    retrieve_and_rank_candidates,
)
from app.services.catalog.provider_cache import (
    CachedRecognitionCatalog,
    recognition_cache,
)
from app.services.catalog.visual_matcher import rerank_by_artwork
from app.services.crop_service import perform_crop_and_warp
from app.services.image_processor import (
    EmptyFileError,
    FileTooLargeError,
    process_and_normalize_image,
    stream_upload_to_temp_file,
)
from app.services.ocr import (
    OcrError,
    OcrTimeoutError,
    OcrUnavailableError,
    get_ocr_engine,
)
from app.services.ocr.pipeline import recognize_card_image

logger = logging.getLogger(__name__)


class ScanSessionError(Exception):
    """Base domain exception for scan sessions."""

    def __init__(
        self,
        message: str = "Scan session error",
        code: str = "SESSION_ERROR",
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class SessionNotFoundError(ScanSessionError):
    """Raised when a scan session does not exist."""

    def __init__(self, message: str = "Scan session not found.") -> None:
        super().__init__(message=message, code="SESSION_NOT_FOUND", status_code=404)


class SessionClosedError(ScanSessionError):
    """Raised when an operation is attempted on an inactive or completed session."""

    def __init__(self, message: str = "Scan session is not active.") -> None:
        super().__init__(message=message, code="SESSION_NOT_ACTIVE", status_code=409)


class ScanSessionService:
    """Domain service managing continuous scan sessions and live capture integration."""

    def __init__(
        self,
        db: Session,
        catalog_service: CardCatalogService | None = None,
    ) -> None:
        self.db = db
        self.catalog_service = catalog_service

    def create_session(self) -> ScanSessionResponse:
        """Create a new active scan session."""
        now_utc = datetime.now(UTC).replace(tzinfo=None)
        session = ScanSession(
            id=str(uuid.uuid4()),
            status="active",
            created_at=now_utc,
            updated_at=now_utc,
            completed_at=None,
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        return ScanSessionResponse(
            id=session.id,
            status=session.status,
            created_at=session.created_at.replace(tzinfo=UTC),
            updated_at=session.updated_at.replace(tzinfo=UTC),
            completed_at=None,
            total_scans=0,
        )

    async def get_session(self, session_id: str) -> ScanSessionDetailResponse:
        """Retrieve full session details including scans and collection state."""
        session = (
            self.db.query(ScanSession).filter(ScanSession.id == session_id).first()
        )
        if session is None:
            raise SessionNotFoundError(f"Scan session '{session_id}' not found.")

        scans = (
            self.db.query(Scan)
            .filter(Scan.session_id == session_id)
            .order_by(Scan.created_at.asc(), Scan.id.asc())
            .all()
        )

        scan_ids = [s.id for s in scans]
        scan_to_linked_item: dict[str, CollectionItem] = {}
        if scan_ids:
            links = (
                self.db.query(CollectionScanLink, CollectionItem)
                .join(
                    CollectionItem,
                    CollectionItem.id == CollectionScanLink.collection_item_id,
                )
                .filter(CollectionScanLink.scan_id.in_(scan_ids))
                .all()
            )
            for link, item in links:
                scan_to_linked_item[link.scan_id] = item

        card_ids: set[str] = set()
        for s in scans:
            if s.confirmed_card_id:
                card_ids.add(s.confirmed_card_id)
            elif (
                s.candidate_matches
                and isinstance(s.candidate_matches, list)
                and len(s.candidate_matches) > 0
            ):
                top_cand = s.candidate_matches[0]
                if isinstance(top_cand, dict) and "id" in top_cand:
                    card_ids.add(top_cand["id"])

        card_id_to_items: dict[str, list[CollectionItem]] = {}
        if card_ids:
            matched_items = (
                self.db.query(CollectionItem)
                .filter(CollectionItem.card_id.in_(list(card_ids)))
                .all()
            )
            for it in matched_items:
                card_id_to_items.setdefault(it.card_id, []).append(it)

        items: list[ScanSessionItemResponse] = []
        for s in scans:
            crop_image_url = (
                f"{settings.API_V1_PREFIX}/scans/{s.id}/crop/image?v={s.crop_version}"
                if s.crop_path
                else None
            )
            image_url = f"{settings.API_V1_PREFIX}/scans/{s.id}/image"

            candidates: list[CandidateMatchItem] = []
            if s.candidate_matches and isinstance(s.candidate_matches, list):
                try:
                    candidates = [serialize_candidate(c) for c in s.candidate_matches]
                except Exception:
                    candidates = []

            best_match = candidates[0] if candidates else None

            confirmed_card = None
            if s.confirmed_card_id and s.card_confirmed_at:
                confirmed_card = ConfirmedCardInfo(
                    id=s.confirmed_card_id,
                    name=s.confirmed_card_name or s.confirmed_card_id,
                    set_name=s.confirmed_card_set_name or "",
                    number=s.confirmed_card_number or "",
                    image_url=s.confirmed_card_image_url,
                    confirmed_at=s.card_confirmed_at.replace(tzinfo=UTC),
                )

            in_coll = False
            coll_qty = 0
            coll_item_id = None

            if s.id in scan_to_linked_item:
                linked_it = scan_to_linked_item[s.id]
                in_coll = True
                coll_qty = linked_it.quantity
                coll_item_id = linked_it.id
            else:
                target_cid = s.confirmed_card_id or (
                    best_match.id if best_match else None
                )
                if target_cid and target_cid in card_id_to_items:
                    matched = card_id_to_items[target_cid]
                    in_coll = True
                    coll_qty = sum(it.quantity for it in matched)
                    coll_item_id = matched[0].id

            items.append(
                ScanSessionItemResponse(
                    scan_id=s.id,
                    session_id=s.session_id,
                    status=s.status,
                    crop_status=s.crop_status,
                    created_at=s.created_at.replace(tzinfo=UTC),
                    image_url=image_url,
                    crop_image_url=crop_image_url,
                    best_match=best_match,
                    candidates=candidates,
                    confirmed_card=confirmed_card,
                    in_collection=in_coll,
                    collection_quantity=coll_qty,
                    collection_item_id=coll_item_id,
                )
            )

        return ScanSessionDetailResponse(
            id=session.id,
            status=session.status,
            created_at=session.created_at.replace(tzinfo=UTC),
            updated_at=session.updated_at.replace(tzinfo=UTC),
            completed_at=(
                session.completed_at.replace(tzinfo=UTC)
                if session.completed_at
                else None
            ),
            total_scans=len(items),
            items=items,
        )

    def complete_session(self, session_id: str) -> ScanSessionResponse:
        """Mark an active session as completed."""
        session = (
            self.db.query(ScanSession).filter(ScanSession.id == session_id).first()
        )
        if session is None:
            raise SessionNotFoundError(f"Scan session '{session_id}' not found.")

        if session.status == "completed":
            total = (
                self.db.query(func.count(Scan.id))
                .filter(Scan.session_id == session_id)
                .scalar()
                or 0
            )
            return ScanSessionResponse(
                id=session.id,
                status=session.status,
                created_at=session.created_at.replace(tzinfo=UTC),
                updated_at=session.updated_at.replace(tzinfo=UTC),
                completed_at=(
                    session.completed_at.replace(tzinfo=UTC)
                    if session.completed_at
                    else None
                ),
                total_scans=total,
            )

        if session.status != "active":
            raise SessionClosedError(
                f"Scan session '{session_id}' is '{session.status}' "
                "and cannot be completed."
            )

        now_utc = datetime.now(UTC).replace(tzinfo=None)
        session.status = "completed"
        session.completed_at = now_utc
        session.updated_at = now_utc
        self.db.commit()
        self.db.refresh(session)

        total = (
            self.db.query(func.count(Scan.id))
            .filter(Scan.session_id == session_id)
            .scalar()
            or 0
        )
        return ScanSessionResponse(
            id=session.id,
            status=session.status,
            created_at=session.created_at.replace(tzinfo=UTC),
            updated_at=session.updated_at.replace(tzinfo=UTC),
            completed_at=session.completed_at.replace(tzinfo=UTC),
            total_scans=total,
        )

    async def capture_frame(
        self,
        session_id: str,
        image_input: UploadFile | bytes,
    ) -> LiveCaptureResponse:
        """Live frame capture, boundary detection, perspective warp, and recognition."""
        session = (
            self.db.query(ScanSession).filter(ScanSession.id == session_id).first()
        )
        if session is None:
            raise SessionNotFoundError(f"Scan session '{session_id}' not found.")

        if session.status != "active":
            raise SessionClosedError(
                f"Scan session '{session_id}' is '{session.status}' "
                "and cannot accept captures."
            )

        scan_id = str(uuid.uuid4())
        storage_dir = Path(settings.UPLOAD_DIRECTORY).resolve()
        storage_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = storage_dir / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        target_path = storage_dir / f"{scan_id}.jpg"
        temp_path: Path | None = None

        try:
            if isinstance(image_input, bytes):
                if len(image_input) == 0:
                    raise EmptyFileError("Uploaded file is empty.")
                if len(image_input) > settings.UPLOAD_MAX_BYTES:
                    raise FileTooLargeError(
                        "File size exceeds maximum limit of "
                        f"{settings.UPLOAD_MAX_BYTES} bytes."
                    )
                temp_path = temp_dir / f"{uuid.uuid4().hex}.tmp"
                temp_path.write_bytes(image_input)
            else:
                temp_path, _ = await stream_upload_to_temp_file(
                    upload_file=image_input,
                    temp_dir=temp_dir,
                    max_bytes=settings.UPLOAD_MAX_BYTES,
                )

            width, height, file_size = await run_in_threadpool(
                process_and_normalize_image,
                source_path=temp_path,
                target_path=target_path,
                max_pixels=settings.UPLOAD_MAX_PIXELS,
                max_dimension=settings.UPLOAD_MAX_DIMENSION,
                jpeg_quality=settings.UPLOAD_JPEG_QUALITY,
            )
        finally:
            if isinstance(image_input, UploadFile):
                await image_input.close()
            if temp_path is not None:
                await run_in_threadpool(temp_path.unlink, missing_ok=True)

        now_utc = datetime.now(UTC)
        expires_at_utc = now_utc + timedelta(hours=settings.UPLOAD_RETENTION_HOURS)

        scan = Scan(
            id=scan_id,
            session_id=session.id,
            status="uploaded",
            image_path=f"{scan_id}.jpg",
            content_type="image/jpeg",
            width=width,
            height=height,
            file_size=file_size,
            created_at=now_utc.replace(tzinfo=None),
            expires_at=expires_at_utc.replace(tzinfo=None),
            crop_status="none",
            crop_version=0,
            rotation=0,
        )
        self.db.add(scan)
        self.db.commit()
        self.db.refresh(scan)

        detected, corners, message, score = await run_in_threadpool(
            detect_card_corners, target_path
        )

        candidates: list[Any] = []
        if detected:
            candidate_filename = f"{scan_id}_crop_{uuid.uuid4().hex}.jpg"
            crop_target_path = storage_dir / candidate_filename
            try:
                crop_w, crop_h, crop_file_size = await run_in_threadpool(
                    perform_crop_and_warp,
                    source_path=target_path,
                    target_path=crop_target_path,
                    corners=corners,
                    rotation=0,
                    max_dimension=2000,
                    jpeg_quality=settings.UPLOAD_JPEG_QUALITY,
                )
                scan.crop_status = "confirmed"
                scan.crop_path = candidate_filename
                scan.crop_width = crop_w
                scan.crop_height = crop_h
                scan.crop_file_size = crop_file_size
                scan.crop_version = 1
                scan.corners = corners.as_dict()
                scan.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
                self.db.commit()
                self.db.refresh(scan)

                recognition_uuid = str(uuid.uuid4())

                def _execute_ocr():
                    return recognize_card_image(crop_target_path, get_ocr_engine())

                try:
                    extracted = await run_in_threadpool(_execute_ocr)
                    scan.recognition_status = "completed"
                    scan.recognition_id = recognition_uuid
                    scan.ocr_crop_version = 1
                    scan.ocr_raw_text = extracted.raw_text
                    scan.recognized_name = extracted.name
                    scan.recognized_number = extracted.number
                    scan.recognized_set_code = extracted.set_code
                    scan.ocr_confidence = extracted.confidence

                    catalog_client = self.catalog_service or get_card_catalog_service()
                    cached_catalog = CachedRecognitionCatalog(
                        catalog_client, recognition_cache
                    )
                    candidates, _ = await retrieve_and_rank_candidates(
                        client=cached_catalog,
                        name=extracted.name,
                        number=extracted.number,
                        set_code=extracted.set_code,
                        alternatives=extracted.alternatives,
                        name_hypotheses=extracted.name_hypotheses,
                        name_confidence=extracted.name_confidence,
                        number_strength=extracted.number_strength,
                        limit=32 if extracted.printed_denominator else 128,
                        extraction=extracted,
                    )
                    if candidates:
                        candidates = await rerank_by_artwork(
                            crop_target_path, candidates
                        )
                    candidates = candidates[:5]

                    candidate_dicts = [
                        c.to_dict()
                        if hasattr(c, "to_dict")
                        else (
                            c.model_dump(mode="json")
                            if hasattr(c, "model_dump")
                            else dict(c)
                        )
                        for c in candidates
                    ]
                    scan.candidate_matches = candidate_dicts
                    scan.search_version = 1
                    scan.catalog_status = "ok"

                    if candidates:
                        top = candidates[0]
                        top_dict = candidate_dicts[0]
                        scan.confirmed_card_id = getattr(
                            top, "id", None
                        ) or top_dict.get("id")
                        scan.confirmed_card_name = getattr(
                            top, "name", None
                        ) or top_dict.get("name")
                        scan.confirmed_card_set_name = getattr(
                            top, "set_name", None
                        ) or top_dict.get("set_name")
                        scan.confirmed_card_number = getattr(
                            top, "local_id", None
                        ) or top_dict.get("local_id")
                        scan.confirmed_card_image_url = getattr(
                            top, "image_url", None
                        ) or top_dict.get("image_url")
                        scan.card_confirmed_at = datetime.now(UTC).replace(tzinfo=None)
                        scan.card_selection_version = 1
                except CatalogUnavailableError as err:
                    logger.warning(
                        "Catalog unavailable during live capture for %s: %s",
                        scan_id,
                        err,
                    )
                    scan.catalog_status = "unavailable"
                    scan.catalog_error = str(err)
                    candidates = []
                except (OcrError, OcrTimeoutError, OcrUnavailableError) as err:
                    logger.warning(
                        "OCR failed during live capture for %s: %s", scan_id, err
                    )
                    scan.recognition_status = "failed"
                    candidates = []
                except Exception as err:
                    logger.exception(
                        "Unexpected error during live recognition for %s: %s",
                        scan_id,
                        err,
                    )
                    scan.recognition_status = "failed"
                    candidates = []

                self.db.commit()
                self.db.refresh(scan)
            except Exception as exc:
                logger.warning(
                    "Auto crop/warp failed for live capture %s: %s", scan_id, exc
                )
                crop_target_path.unlink(missing_ok=True)
                detected = False
        else:
            scan.crop_status = "none"
            scan.corners = corners.as_dict() if corners else None
            self.db.commit()
            self.db.refresh(scan)
            candidates = []

        serialized_candidates = [serialize_candidate(c) for c in candidates]
        best_match = serialized_candidates[0] if serialized_candidates else None

        in_coll = False
        coll_qty = 0
        coll_item_id = None

        if best_match:
            coll_items = (
                self.db.query(CollectionItem)
                .filter(CollectionItem.card_id == best_match.id)
                .all()
            )
            if coll_items:
                in_coll = True
                coll_qty = sum(item.quantity for item in coll_items)
                coll_item_id = coll_items[0].id

        session.updated_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.commit()
        self.db.refresh(session)

        scan_resp = build_scan_response(scan)
        return LiveCaptureResponse(
            scan=scan_resp,
            detected=detected,
            corners=corners,
            candidates=serialized_candidates,
            best_match=best_match,
            in_collection=in_coll,
            collection_quantity=coll_qty,
            collection_item_id=coll_item_id,
            session_id=session.id,
            session_status=session.status,
        )


def get_scan_session_service(
    db: Session = Depends(get_db),
    catalog_service: CardCatalogService = Depends(get_card_catalog_service),
) -> ScanSessionService:
    """FastAPI dependency provider for ScanSessionService."""
    return ScanSessionService(db=db, catalog_service=catalog_service)
