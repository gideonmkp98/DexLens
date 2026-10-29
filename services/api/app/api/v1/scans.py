import logging
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.v1.cards import _derive_image_urls
from app.core.config import settings
from app.core.database import get_db
from app.integrations.tcgdex.mapper import is_digital_card
from app.models.scan import Scan
from app.schemas.scan import (
    CandidateMatchItem,
    ConfirmCardRequest,
    ConfirmCropRequest,
    ConfirmedCardInfo,
    CropCorners,
    CropRequest,
    DetectResponse,
    FieldEvidenceModel,
    ImageQualityModel,
    RecognitionEvidenceModel,
    RecognizeResponse,
    ResetCardConfirmationRequest,
    ScanResponse,
    SearchCandidatesRequest,
    SearchCandidatesResponse,
)
from app.services.card_catalog import (
    CardCatalogService,
    get_card_catalog_service,
)
from app.services.card_detector import (
    InvalidCornersError,
    detect_card_corners,
    validate_corners,
)
from app.services.catalog import (
    CandidateMatch,
    CatalogUnavailableError,
    derive_confidence_state,
    retrieve_and_rank_candidates,
)
from app.services.catalog.provider_cache import (
    CachedRecognitionCatalog,
    recognition_cache,
)
from app.services.catalog.visual_matcher import rerank_by_artwork
from app.services.crop_service import CropProcessingError, perform_crop_and_warp
from app.services.image_processor import (
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

router = APIRouter(prefix="/scans", tags=["Scans"])


def _validate_uuid(val: str) -> str:
    """Validate that val is a valid UUID string to prevent path traversal."""
    try:
        parsed = uuid.UUID(val)
        return str(parsed)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
        ) from None


def _get_storage_dir() -> Path:
    storage_dir = Path(settings.UPLOAD_DIRECTORY).resolve()
    storage_dir.mkdir(parents=True, exist_ok=True)
    return storage_dir


def _serialize_candidate(c: object) -> CandidateMatchItem:
    if isinstance(c, CandidateMatchItem):
        return c
    if isinstance(c, dict):
        return CandidateMatchItem.model_validate(c)
    return CandidateMatchItem(
        id=getattr(c, "id", ""),
        name=getattr(c, "name", ""),
        local_id=getattr(c, "local_id", ""),
        set_id=getattr(c, "set_id", ""),
        set_name=getattr(c, "set_name", ""),
        image_url=getattr(c, "image_url", None),
        score=getattr(c, "score", 0),
        reasons=getattr(c, "reasons", []),
        hp=getattr(c, "hp", None),
        matched_attacks=getattr(c, "matched_attacks", []),
        matched_abilities=getattr(c, "matched_abilities", []),
        visual_similarity=getattr(c, "visual_similarity", None),
    )


def _build_scan_response(scan: Scan) -> ScanResponse:
    crop_image_url = None
    if scan.crop_path:
        crop_image_url = f"/api/v1/scans/{scan.id}/crop/image?v={scan.crop_version}"

    corners_obj = None
    if scan.corners:
        try:
            corners_obj = CropCorners.model_validate(scan.corners)
        except Exception:
            corners_obj = None

    confirmed_card = None
    if scan.confirmed_card_id and scan.card_confirmed_at:
        confirmed_card = ConfirmedCardInfo(
            id=scan.confirmed_card_id,
            name=scan.confirmed_card_name or scan.confirmed_card_id,
            set_name=scan.confirmed_card_set_name or "",
            number=scan.confirmed_card_number or "",
            image_url=scan.confirmed_card_image_url,
            confirmed_at=scan.card_confirmed_at.replace(tzinfo=UTC),
        )

    candidates = None
    if scan.candidate_matches:
        try:
            candidates = [_serialize_candidate(c) for c in scan.candidate_matches]
        except Exception:
            candidates = None

    image_quality = None
    if scan.crop_width and scan.crop_height:
        is_low = scan.crop_width < 400 or scan.crop_height < 550
        image_quality = ImageQualityModel(
            width=scan.crop_width,
            height=scan.crop_height,
            is_low_res=is_low,
            warning=(
                f"Lage uitsnederesolutie ({scan.crop_width}x{scan.crop_height}px). "
                f"Fijne details van verzamelnummers kunnen onduidelijk zijn."
            )
            if is_low
            else None,
            guidance=(
                "Upload een scherpere foto waarbij de kaart meer van het beeld vult, "
                "met minimale reflectie of schaduw."
            )
            if is_low
            else None,
        )

    cand_matches_for_scoring = []
    if candidates:
        for c in candidates:
            cand_matches_for_scoring.append(
                CandidateMatch(
                    id=c.id,
                    name=c.name,
                    local_id=c.local_id,
                    set_id=c.set_id,
                    set_name=c.set_name,
                    image_url=c.image_url,
                    score=c.score,
                    reasons=c.reasons,
                    hp=getattr(c, "hp", None),
                    matched_attacks=getattr(c, "matched_attacks", []) or [],
                    matched_abilities=getattr(c, "matched_abilities", []) or [],
                    visual_similarity=getattr(c, "visual_similarity", None),
                )
            )

    confidence_state = derive_confidence_state(
        cand_matches_for_scoring,
        is_low_res=image_quality.is_low_res if image_quality else False,
    )

    evidence = None
    if (
        scan.recognized_name
        or scan.recognized_number
        or scan.recognized_set_code
        or image_quality
    ):
        evidence = RecognitionEvidenceModel(
            name=FieldEvidenceModel(
                raw_text=scan.recognized_name,
                normalized=scan.recognized_name,
                confidence_level="high"
                if scan.recognized_name and len(scan.recognized_name) >= 4
                else ("medium" if scan.recognized_name else "low"),
                source_region="header",
                alternatives=[],
            ),
            number=FieldEvidenceModel(
                raw_text=scan.recognized_number,
                normalized=scan.recognized_number,
                confidence_level="high"
                if (scan.recognized_number and "/" in scan.recognized_number)
                else ("medium" if scan.recognized_number else "low"),
                source_region="footer",
                alternatives=[],
            ),
            denominator=FieldEvidenceModel(
                raw_text=scan.recognized_number.split("/")[1]
                if scan.recognized_number and "/" in scan.recognized_number
                else None,
                normalized=scan.recognized_number.split("/")[1]
                if scan.recognized_number and "/" in scan.recognized_number
                else None,
                confidence_level="high"
                if scan.recognized_number and "/" in scan.recognized_number
                else "low",
                source_region="footer",
            ),
            set_info=FieldEvidenceModel(
                raw_text=scan.recognized_set_code,
                normalized=scan.recognized_set_code,
                confidence_level="high" if scan.recognized_set_code else "low",
                source_region="footer",
            ),
            image_quality=image_quality
            or ImageQualityModel(width=scan.width, height=scan.height),
            hp=None,
            attacks=[],
            abilities=[],
        )

    if scan.recognition_evidence:
        try:
            evidence = RecognitionEvidenceModel.model_validate(
                scan.recognition_evidence
            )
        except Exception:
            pass

    return ScanResponse(
        id=scan.id,
        status=scan.status,
        image_url=f"/api/v1/scans/{scan.id}/image",
        width=scan.width,
        height=scan.height,
        content_type=scan.content_type,
        file_size=scan.file_size,
        created_at=scan.created_at.replace(tzinfo=UTC),
        expires_at=scan.expires_at.replace(tzinfo=UTC),
        crop_status=scan.crop_status or "none",
        corners=corners_obj,
        rotation=scan.rotation or 0,
        crop_image_url=crop_image_url,
        crop_width=scan.crop_width,
        crop_height=scan.crop_height,
        crop_file_size=scan.crop_file_size,
        crop_version=scan.crop_version or 0,
        confirmed_at=(
            scan.confirmed_at.replace(tzinfo=UTC) if scan.confirmed_at else None
        ),
        recognition_status=scan.recognition_status or "none",
        recognition_id=scan.recognition_id,
        ocr_crop_version=scan.ocr_crop_version,
        ocr_raw_text=scan.ocr_raw_text,
        recognized_name=scan.recognized_name,
        recognized_number=scan.recognized_number,
        recognized_set_code=scan.recognized_set_code,
        ocr_confidence=scan.ocr_confidence,
        confidence_state=confidence_state,
        image_quality=image_quality,
        evidence=evidence,
        search_version=scan.search_version or 0,
        candidate_search_version=scan.search_version or 0,
        card_selection_version=scan.card_selection_version or 0,
        catalog_status=scan.catalog_status or "none",
        catalog_error=scan.catalog_error,
        user_search_name=scan.user_search_name,
        user_search_number=scan.user_search_number,
        user_search_set_code=scan.user_search_set_code,
        user_search_provider_set_id=scan.user_search_provider_set_id,
        candidates=candidates,
        confirmed_card=confirmed_card,
    )


def _get_active_scan(scan_id: str, db: Session) -> tuple[Scan, Path]:
    """Retrieve scan and verify expiration and storage file presence."""
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    if not scan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
        )

    now_utc = datetime.now(UTC)
    scan_expires_at = scan.expires_at.replace(tzinfo=UTC)
    if scan_expires_at <= now_utc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
        )

    storage_dir = _get_storage_dir()
    file_path = (storage_dir / scan.image_path).resolve()
    if not file_path.is_relative_to(storage_dir) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "IMAGE_NOT_FOUND",
                "message": "Scan image not found on disk.",
            },
        )

    return scan, file_path


@router.post("", response_model=ScanResponse, status_code=status.HTTP_201_CREATED)
async def upload_scan(
    request: Request,
    file: UploadFile = File(..., description="Card image to upload and normalize"),
    db: Session = Depends(get_db),
) -> ScanResponse:
    """Upload a single image, validate and normalize it, and store metadata."""
    form = await request.form()
    if (
        sum(isinstance(value, StarletteUploadFile) for _, value in form.multi_items())
        != 1
    ):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MULTIPLE_FILES",
                "message": "Please upload exactly one image.",
            },
        )
    scan_id = str(uuid.uuid4())
    temp_path = None
    try:
        storage_dir = await run_in_threadpool(_get_storage_dir)
        temp_dir = storage_dir / ".tmp"
        target_path = storage_dir / f"{scan_id}.jpg"
        temp_path, _ = await stream_upload_to_temp_file(
            upload_file=file,
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
    except OSError as exc:
        logger.exception("Failed to store scan %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "STORAGE_ERROR",
                "message": "Unable to store image. Please try again.",
            },
        ) from exc
    finally:
        await file.close()
        if temp_path is not None:
            await run_in_threadpool(temp_path.unlink, missing_ok=True)

    return await run_in_threadpool(
        _persist_scan, db, scan_id, target_path, width, height, file_size
    )


def _persist_scan(
    db: Session,
    scan_id: str,
    target_path: Path,
    width: int,
    height: int,
    file_size: int,
) -> ScanResponse:
    now_utc = datetime.now(UTC)
    expires_at_utc = now_utc + timedelta(hours=settings.UPLOAD_RETENTION_HOURS)

    scan = Scan(
        id=scan_id,
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

    response = ScanResponse(
        id=scan_id,
        status="uploaded",
        image_url=f"{settings.API_V1_PREFIX}/scans/{scan_id}/image",
        width=width,
        height=height,
        content_type="image/jpeg",
        file_size=file_size,
        created_at=now_utc,
        expires_at=expires_at_utc,
        crop_status="none",
        crop_version=0,
        rotation=0,
        recognition_status="none",
        recognition_id=None,
        ocr_crop_version=None,
        recognition_evidence=None,
        ocr_raw_text=None,
        recognized_name=None,
        recognized_number=None,
        recognized_set_code=None,
        ocr_confidence=None,
        search_version=0,
        candidate_search_version=0,
        card_selection_version=0,
        catalog_status="none",
        catalog_error=None,
        user_search_name=None,
        user_search_number=None,
        user_search_set_code=None,
        user_search_provider_set_id=None,
        candidates=None,
        confirmed_card=None,
    )
    try:
        db.add(scan)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            target_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Failed to remove uncommitted scan image %s", scan_id)
        logger.exception("Failed to commit scan %s: %s", scan_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to persist scan record.",
            },
        ) from exc

    return response


@router.get("/{id}", response_model=ScanResponse)
def get_scan(
    id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ScanResponse:
    """Retrieve scan metadata by ID, including crop status and coordinates."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, _ = _get_active_scan(scan_id, db)
    return _build_scan_response(scan)


@router.get("/{id}/image")
def get_scan_image(
    id: str,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve the normalized original scan image with no-store caching headers."""
    scan_id = _validate_uuid(id)
    scan, file_path = _get_active_scan(scan_id, db)

    return FileResponse(
        path=str(file_path),
        media_type=scan.content_type,
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{id}/detect", response_model=DetectResponse)
async def detect_scan_card(
    id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> DetectResponse:
    """Detect card contour corners automatically in the stored scan image."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, file_path = _get_active_scan(scan_id, db)

    detected, corners, message, score = await run_in_threadpool(
        detect_card_corners, file_path
    )

    # Recheck expiration transactionally before publishing detection result to DB
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    if detected:
        stmt = (
            update(Scan)
            .where(
                Scan.id == scan_id,
                Scan.crop_status.in_(["none", "detected"]),
                Scan.expires_at > now_utc,
            )
            .values(
                crop_status="detected",
                corners=corners.as_dict(),
            )
        )
        res = db.execute(stmt)
        if res.rowcount == 0:
            # Check if scan expired or was deleted during detection
            curr = db.query(Scan).filter(Scan.id == scan_id).first()
            if curr is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            # If scan status is already 'preview' or 'confirmed', preserve that state
        else:
            db.commit()

    return DetectResponse(
        detected=detected,
        corners=corners,
        message=message,
        score=score,
    )


@router.post("/{id}/crop", response_model=ScanResponse)
async def crop_scan_card(
    id: str,
    body: CropRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ScanResponse:
    """Generate a perspective-corrected rectangular card crop from 4 corners."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, source_path = _get_active_scan(scan_id, db)

    initial_crop_status = scan.crop_status
    previous_crop_path = scan.crop_path

    if body.rotation not in (0, 90, 180, 270):
        raise HTTPException(
            status_code=422,
            detail={
                "code": "INVALID_ROTATION",
                "message": "Rotation must be 0, 90, 180, or 270 degrees.",
            },
        )

    try:
        validate_corners(body.corners)
    except InvalidCornersError as err:
        raise HTTPException(
            status_code=422,
            detail={"code": err.code, "message": err.message},
        ) from err

    storage_dir = await run_in_threadpool(_get_storage_dir)

    # Issue 1: Generate into a unique candidate filename to never overwrite
    # an existing valid crop before database commit succeeds
    candidate_filename = f"{scan_id}_crop_{uuid.uuid4().hex}.jpg"
    target_path = storage_dir / candidate_filename

    try:
        crop_w, crop_h, file_size = await run_in_threadpool(
            perform_crop_and_warp,
            source_path=source_path,
            target_path=target_path,
            corners=body.corners,
            rotation=body.rotation,
            max_dimension=2000,
            jpeg_quality=settings.UPLOAD_JPEG_QUALITY,
        )
    except CropProcessingError as err:
        target_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=422,
            detail={"code": err.code, "message": err.message},
        ) from err
    except Exception as exc:
        target_path.unlink(missing_ok=True)
        logger.exception("Failed to generate crop for scan %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "CROP_ERROR",
                "message": "Failed to generate card crop. Please try again.",
            },
        ) from exc

    # Issue 2 & 4: Atomic conditional update rechecking expiration,
    # required expected version, and confirmation state
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    expected_ver = body.expected_version

    where_clauses = [
        Scan.id == scan_id,
        Scan.crop_version == expected_ver,
        Scan.expires_at > now_utc,
    ]
    # A request started while scan was unconfirmed must not overwrite confirmation
    if initial_crop_status != "confirmed":
        where_clauses.append(Scan.crop_status != "confirmed")

    stmt = (
        update(Scan)
        .where(*where_clauses)
        .values(
            crop_status="preview",
            crop_path=candidate_filename,
            crop_width=crop_w,
            crop_height=crop_h,
            crop_file_size=file_size,
            crop_version=Scan.crop_version + 1,
            corners=body.corners.as_dict(),
            rotation=body.rotation,
            confirmed_at=None,
            recognition_status="none",
            recognition_id=None,
            ocr_crop_version=None,
            recognition_evidence=None,
            ocr_raw_text=None,
            recognized_name=None,
            recognized_number=None,
            recognized_set_code=None,
            ocr_confidence=None,
            candidate_matches=None,
            confirmed_card_id=None,
            confirmed_card_name=None,
            confirmed_card_set_name=None,
            confirmed_card_number=None,
            confirmed_card_image_url=None,
            card_confirmed_at=None,
            search_version=0,
            card_selection_version=0,
            catalog_status="none",
            catalog_error=None,
            user_search_name=None,
            user_search_number=None,
            user_search_set_code=None,
            user_search_provider_set_id=None,
        )
    )

    try:
        res = db.execute(stmt)
        if res.rowcount == 0:
            db.rollback()
            target_path.unlink(missing_ok=True)

            curr = db.query(Scan).filter(Scan.id == scan_id).first()
            if curr is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            if curr.crop_status == "confirmed" and initial_crop_status != "confirmed":
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "CONFIRMED_CONFLICT",
                        "message": (
                            "Scan was confirmed while crop was processing. "
                            "Confirmation preserved."
                        ),
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_VERSION",
                    "message": (
                        "The scan crop state has changed or was modified concurrently. "
                        "Please reload and try again."
                    ),
                },
            )

        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        target_path.unlink(missing_ok=True)
        logger.exception("Failed to publish crop record for %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to save crop state in database.",
            },
        ) from exc

    # On successful commit, safely remove superseded crop file if present
    if previous_crop_path and previous_crop_path != candidate_filename:
        old_file = (storage_dir / previous_crop_path).resolve()
        if old_file.is_relative_to(storage_dir) and old_file.is_file():
            try:
                old_file.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not unlink superseded crop file %s", old_file)

    db.refresh(scan)
    return _build_scan_response(scan)


@router.post("/{id}/confirm", response_model=ScanResponse)
def confirm_scan_crop(
    id: str,
    body: ConfirmCropRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ScanResponse:
    """Confirm current preview with atomic conditional update on version and path."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    now_utc = datetime.now(UTC).replace(tzinfo=None)

    # 1. Fetch current scan state to validate file before modifying database
    curr = db.query(Scan).filter(Scan.id == scan_id).first()
    if curr is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
        )
    if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
        raise HTTPException(
            status_code=404,
            detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
        )
    if not curr.crop_path or curr.crop_status == "none":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "NO_PREVIEW_AVAILABLE",
                "message": (
                    "No crop preview available to confirm. Generate a preview first."
                ),
            },
        )
    if curr.crop_version != body.crop_version or curr.crop_status != "preview":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_VERSION",
                "message": (
                    "The crop preview has changed or is out of date. "
                    "Please generate a new preview before confirming."
                ),
            },
        )

    # 2. Validate physical file existence and path traversal before update
    storage_dir = _get_storage_dir()
    candidate_crop_path = curr.crop_path
    crop_file = (storage_dir / candidate_crop_path).resolve()
    if not crop_file.is_relative_to(storage_dir) or not crop_file.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CROP_NOT_FOUND",
                "message": "Cropped image file not found on disk.",
            },
        )

    # 3. Atomic conditional update: bind confirmation to this EXACT verified crop path,
    # revision, preview status, and unexpired timestamp
    stmt = (
        update(Scan)
        .where(
            Scan.id == scan_id,
            Scan.crop_version == body.crop_version,
            Scan.crop_path == candidate_crop_path,
            Scan.crop_status == "preview",
            Scan.expires_at > now_utc,
        )
        .values(
            crop_status="confirmed",
            confirmed_at=now_utc,
            crop_version=Scan.crop_version + 1,
            recognition_status="none",
            recognition_id=None,
            ocr_crop_version=None,
            recognition_evidence=None,
            ocr_raw_text=None,
            recognized_name=None,
            recognized_number=None,
            recognized_set_code=None,
            ocr_confidence=None,
            candidate_matches=None,
            search_version=0,
            card_selection_version=0,
            catalog_status="none",
            catalog_error=None,
            user_search_name=None,
            user_search_number=None,
            user_search_set_code=None,
            user_search_provider_set_id=None,
            confirmed_card_id=None,
            confirmed_card_name=None,
            confirmed_card_set_name=None,
            confirmed_card_number=None,
            confirmed_card_image_url=None,
            card_confirmed_at=None,
        )
    )

    try:
        res = db.execute(stmt)
        if res.rowcount == 0:
            db.rollback()
            recheck = db.query(Scan).filter(Scan.id == scan_id).first()
            if recheck is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if recheck.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            if (
                recheck.crop_version != body.crop_version
                or recheck.crop_path != candidate_crop_path
                or recheck.crop_status != "preview"
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_VERSION",
                        "message": (
                            "The crop preview has changed or was replaced. "
                            "Please generate a new preview before confirming."
                        ),
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "CONFIRM_CONFLICT",
                    "message": "Unable to confirm crop due to conflicting update.",
                },
            )

        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to confirm crop for %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to update confirmation state.",
            },
        ) from exc

    db.expire_all()
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    return _build_scan_response(scan)


@router.get("/{id}/crop/image")
def get_scan_crop_image(
    id: str,
    v: int | None = None,
    db: Session = Depends(get_db),
) -> FileResponse:
    """Serve the perspective-corrected cropped card image without caching."""
    scan_id = _validate_uuid(id)
    scan, _ = _get_active_scan(scan_id, db)

    if not scan.crop_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CROP_NOT_FOUND",
                "message": "No cropped image exists for this scan.",
            },
        )

    # Optional version check for client cache busting and strict verification
    if v is not None and scan.crop_version != v:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CROP_VERSION_MISMATCH",
                "message": (
                    f"Requested crop version {v} does not match "
                    f"current version {scan.crop_version}."
                ),
            },
        )

    storage_dir = _get_storage_dir()
    file_path = (storage_dir / scan.crop_path).resolve()
    if not file_path.is_relative_to(storage_dir) or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "CROP_NOT_FOUND",
                "message": "Cropped image not found on disk.",
            },
        )

    return FileResponse(
        path=str(file_path),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/{id}/recognize", response_model=RecognizeResponse)
async def recognize_card(
    id: str,
    response: Response,
    db: Session = Depends(get_db),
    client: CardCatalogService = Depends(get_card_catalog_service),
) -> RecognizeResponse:
    """Run OCR text extraction and catalog matching on the confirmed crop."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, _ = _get_active_scan(scan_id, db)

    if scan.crop_status != "confirmed" or not scan.crop_path:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CROP_NOT_CONFIRMED",
                "message": "Card crop must be confirmed before recognition.",
            },
        )

    storage_dir = _get_storage_dir()
    crop_file_path = (storage_dir / scan.crop_path).resolve()
    if not crop_file_path.is_relative_to(storage_dir) or not crop_file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CROP_NOT_FOUND",
                "message": "Cropped image file not found on disk.",
            },
        )

    crop_version_analyzed = scan.crop_version
    initial_search_version = scan.search_version
    recognition_uuid = str(uuid.uuid4())

    def _execute_ocr():
        return recognize_card_image(crop_file_path, get_ocr_engine())

    try:
        extracted = await run_in_threadpool(_execute_ocr)
    except OcrUnavailableError as err:
        logger.exception("OCR engine unavailable for scan %s", scan_id)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "OCR_UNAVAILABLE",
                "message": "OCR recognition engine is temporarily unavailable.",
            },
        ) from err
    except OcrTimeoutError as err:
        logger.warning("OCR recognition timed out for scan %s", scan_id)
        raise HTTPException(
            status_code=504,
            detail={
                "code": "OCR_TIMEOUT",
                "message": "Card text recognition timed out. Please try again.",
            },
        ) from err
    except OcrError as err:
        logger.exception("OCR recognition error for scan %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "OCR_ERROR",
                "message": "Failed to process card text recognition.",
            },
        ) from err

    # Retrieve and rank catalog candidates
    catalog_status = "ok"
    catalog_error = None
    try:
        candidates, total_count = await retrieve_and_rank_candidates(
            client=CachedRecognitionCatalog(client, recognition_cache),
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
            candidates = await rerank_by_artwork(crop_file_path, candidates)
        candidates = candidates[:5]
    except CatalogUnavailableError as err:
        logger.warning(
            "Catalog unavailable during recognition for %s: %s", scan_id, err
        )
        candidates, total_count = [], 0
        catalog_status = "unavailable"
        catalog_error = str(err)

    img_q = extracted.image_quality or {}
    image_quality_model = ImageQualityModel(
        width=img_q.get("width", scan.crop_width or scan.width),
        height=img_q.get("height", scan.crop_height or scan.height),
        is_low_res=img_q.get("is_low_res", False),
        warning=img_q.get("warning"),
        guidance=img_q.get("guidance"),
    )
    confidence_state = derive_confidence_state(
        candidates, is_low_res=image_quality_model.is_low_res
    )
    evidence_model = RecognitionEvidenceModel(
        name=FieldEvidenceModel(
            raw_text=extracted.name,
            normalized=extracted.name,
            confidence_level=extracted.name_confidence,
            source_region=extracted.source_regions.get("name", "header"),
            alternatives=extracted.name_hypotheses,
        ),
        number=FieldEvidenceModel(
            raw_text=extracted.number,
            normalized=extracted.number,
            confidence_level="high"
            if extracted.number_strength == "strong"
            else ("medium" if extracted.number_strength == "moderate" else "low"),
            source_region=extracted.source_regions.get("number", "footer"),
            alternatives=extracted.alternatives,
        ),
        denominator=FieldEvidenceModel(
            raw_text=extracted.printed_denominator,
            normalized=extracted.printed_denominator,
            confidence_level="high" if extracted.printed_denominator else "low",
            source_region=extracted.source_regions.get("number", "footer"),
        ),
        set_info=FieldEvidenceModel(
            raw_text=extracted.set_code,
            normalized=extracted.set_code,
            confidence_level="high" if extracted.set_code else "low",
            source_region=extracted.source_regions.get("set_code", "footer"),
        ),
        image_quality=image_quality_model,
        hp=extracted.hp,
        attacks=extracted.attacks,
        abilities=extracted.abilities,
    )

    candidate_items = [_serialize_candidate(c) for c in candidates]
    candidate_dicts = [item.model_dump(mode="json") for item in candidate_items]
    now_utc = datetime.now(UTC).replace(tzinfo=None)

    # Concurrency control:
    # If search_version is unchanged since recognition started, publish candidates.
    # If search_version changed (user initiated manual search during OCR),
    # preserve user search results and only publish OCR extracted text and status.
    update_candidates_stmt = (
        update(Scan)
        .where(
            Scan.id == scan_id,
            Scan.crop_version == crop_version_analyzed,
            Scan.crop_status == "confirmed",
            Scan.search_version == initial_search_version,
            Scan.expires_at > now_utc,
        )
        .values(
            recognition_status="completed",
            recognition_id=recognition_uuid,
            ocr_crop_version=crop_version_analyzed,
            recognition_evidence=evidence_model.model_dump(mode="json"),
            ocr_raw_text=extracted.raw_text,
            recognized_name=extracted.name,
            recognized_number=extracted.number,
            recognized_set_code=extracted.set_code,
            ocr_confidence=extracted.confidence,
            candidate_matches=candidate_dicts,
            search_version=Scan.search_version + 1,
            catalog_status=catalog_status,
            catalog_error=catalog_error,
        )
    )

    update_ocr_only_stmt = (
        update(Scan)
        .where(
            Scan.id == scan_id,
            Scan.crop_version == crop_version_analyzed,
            Scan.crop_status == "confirmed",
            Scan.expires_at > now_utc,
        )
        .values(
            recognition_status="completed",
            recognition_id=recognition_uuid,
            ocr_crop_version=crop_version_analyzed,
            recognition_evidence=evidence_model.model_dump(mode="json"),
            ocr_raw_text=extracted.raw_text,
            recognized_name=extracted.name,
            recognized_number=extracted.number,
            recognized_set_code=extracted.set_code,
            ocr_confidence=extracted.confidence,
        )
    )

    try:
        res = db.execute(update_candidates_stmt)
        if res.rowcount == 0:
            curr = db.query(Scan).filter(Scan.id == scan_id).first()
            if curr is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            if (
                curr.crop_version != crop_version_analyzed
                or curr.crop_status != "confirmed"
            ):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_VERSION",
                        "message": (
                            "Crop version changed while recognition was processing."
                        ),
                    },
                )
            # User performed search while OCR ran; preserve search & record OCR only
            res_ocr = db.execute(update_ocr_only_stmt)
            if res_ocr.rowcount == 0:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_VERSION",
                        "message": (
                            "Crop version changed while recognition was processing."
                        ),
                    },
                )
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to persist recognition for %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to save card recognition state.",
            },
        ) from exc

    db.expire_all()
    latest_scan = db.query(Scan).filter(Scan.id == scan_id).first()
    candidate_items = [CandidateMatchItem.model_validate(c) for c in candidate_dicts]

    return RecognizeResponse(
        recognition_id=recognition_uuid,
        crop_version=crop_version_analyzed,
        raw_text=extracted.raw_text,
        recognized_name=extracted.name,
        recognized_number=extracted.number,
        recognized_set_code=extracted.set_code,
        ocr_confidence=extracted.confidence,
        confidence_state=confidence_state,
        image_quality=image_quality_model,
        evidence=evidence_model,
        catalog_status=catalog_status,
        catalog_error=catalog_error,
        search_version=latest_scan.search_version if latest_scan else 0,
        card_selection_version=(
            latest_scan.card_selection_version if latest_scan else 0
        ),
        candidates=candidate_items,
        total_candidates=total_count,
    )


@router.post("/{id}/search-candidates", response_model=SearchCandidatesResponse)
async def search_card_candidates(
    id: str,
    body: SearchCandidatesRequest,
    response: Response,
    db: Session = Depends(get_db),
    client: CardCatalogService = Depends(get_card_catalog_service),
) -> SearchCandidatesResponse:
    """Search catalog candidates using user-edited or manual search values."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, _ = _get_active_scan(scan_id, db)

    if scan.crop_version != body.expected_crop_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_VERSION",
                "message": "The crop has changed. Please refresh your search.",
            },
        )

    if (
        body.expected_search_version is not None
        and scan.search_version != body.expected_search_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_SEARCH_VERSION",
                "message": "A newer search has already occurred. Please refresh.",
            },
        )

    try:
        candidates, total_count = await retrieve_and_rank_candidates(
            client=client,
            name=body.name,
            number=body.number,
            set_id=body.set_id,
            set_code=body.set_code,
            limit=10,
        )
    except CatalogUnavailableError as err:
        logger.exception(
            "Catalog provider error during candidate search for %s", scan_id
        )
        raise HTTPException(
            status_code=503,
            detail={
                "code": "CATALOG_UNAVAILABLE",
                "message": "Card catalog provider is temporarily unreachable.",
            },
        ) from err

    candidate_items = [_serialize_candidate(c) for c in candidates]
    candidate_dicts = [item.model_dump(mode="json") for item in candidate_items]
    now_utc = datetime.now(UTC).replace(tzinfo=None)

    where_clauses = [
        Scan.id == scan_id,
        Scan.crop_version == body.expected_crop_version,
        Scan.expires_at > now_utc,
    ]
    if body.expected_search_version is not None:
        where_clauses.append(Scan.search_version == body.expected_search_version)

    stmt = (
        update(Scan)
        .where(*where_clauses)
        .values(
            candidate_matches=candidate_dicts,
            search_version=Scan.search_version + 1,
            user_search_name=body.name,
            user_search_number=body.number,
            user_search_set_code=body.set_code,
            user_search_provider_set_id=body.set_id,
            catalog_status="ok",
            catalog_error=None,
        )
    )

    try:
        res = db.execute(stmt)
        if res.rowcount == 0:
            db.rollback()
            curr = db.query(Scan).filter(Scan.id == scan_id).first()
            if curr is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            if curr.crop_version != body.expected_crop_version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_VERSION",
                        "message": "Crop version changed while search was in progress.",
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_SEARCH_VERSION",
                    "message": "Search version changed concurrently. Please refresh.",
                },
            )
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to update candidate matches for %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to update candidate matches.",
            },
        ) from exc

    db.expire_all()
    latest_scan = db.query(Scan).filter(Scan.id == scan_id).first()
    candidate_items = [CandidateMatchItem.model_validate(c) for c in candidate_dicts]
    is_low_res = bool(
        (scan.crop_width and scan.crop_width < 400)
        or (scan.crop_height and scan.crop_height < 550)
    )
    search_conf_state = derive_confidence_state(candidates, is_low_res=is_low_res)
    return SearchCandidatesResponse(
        search_version=(
            latest_scan.search_version
            if latest_scan
            else (body.expected_search_version or 0) + 1
        ),
        crop_version=body.expected_crop_version,
        confidence_state=search_conf_state,
        catalog_status="ok",
        candidates=candidate_items,
        total_candidates=total_count,
    )


@router.post("/{id}/confirm-card", response_model=ScanResponse)
async def confirm_catalog_card(
    id: str,
    body: ConfirmCardRequest,
    response: Response,
    db: Session = Depends(get_db),
    client: CardCatalogService = Depends(get_card_catalog_service),
) -> ScanResponse:
    """Explicitly confirm a chosen catalog card with atomic version binding."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, _ = _get_active_scan(scan_id, db)

    if scan.crop_status != "confirmed":
        raise HTTPException(
            status_code=400,
            detail={
                "code": "CROP_NOT_CONFIRMED",
                "message": "Crop must be confirmed before confirming a catalog card.",
            },
        )

    if scan.crop_version != body.expected_crop_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_VERSION",
                "message": (
                    "The crop state has changed. Please review candidates again."
                ),
            },
        )

    if (
        body.expected_search_version is not None
        and scan.search_version != body.expected_search_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_SEARCH_VERSION",
                "message": (
                    "The candidate search results have changed. "
                    "Please review candidates again."
                ),
            },
        )

    if (
        body.expected_selection_version is not None
        and scan.card_selection_version != body.expected_selection_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_SELECTION_VERSION",
                "message": (
                    "Card confirmation state has changed. "
                    "Please review current selection."
                ),
            },
        )

    # Server-side validation of selected card against catalog provider
    card_data = await client.get_card(body.card_id)
    if not card_data or not isinstance(card_data, dict) or is_digital_card(card_data):
        raise HTTPException(
            status_code=404,
            detail={
                "code": "CARD_NOT_FOUND",
                "message": "The selected card could not be found in the catalog.",
            },
        )

    card_name = str(card_data.get("name", body.card_id))
    local_id = str(card_data.get("localId", ""))
    set_obj = card_data.get("set", {})
    set_name = str(set_obj.get("name", "")) if isinstance(set_obj, dict) else ""

    raw_img = card_data.get("image")
    small_img, _ = _derive_image_urls(raw_img) if raw_img else (None, None)

    now_utc = datetime.now(UTC).replace(tzinfo=None)

    where_clauses = [
        Scan.id == scan_id,
        Scan.crop_version == body.expected_crop_version,
        Scan.crop_status == "confirmed",
        Scan.expires_at > now_utc,
    ]
    if body.expected_search_version is not None:
        where_clauses.append(Scan.search_version == body.expected_search_version)
    if body.expected_selection_version is not None:
        where_clauses.append(
            Scan.card_selection_version == body.expected_selection_version
        )

    stmt = (
        update(Scan)
        .where(*where_clauses)
        .values(
            confirmed_card_id=body.card_id,
            confirmed_card_name=card_name,
            confirmed_card_set_name=set_name,
            confirmed_card_number=local_id,
            confirmed_card_image_url=small_img,
            card_confirmed_at=now_utc,
            card_selection_version=Scan.card_selection_version + 1,
        )
    )

    try:
        res = db.execute(stmt)
        if res.rowcount == 0:
            db.rollback()
            curr = db.query(Scan).filter(Scan.id == scan_id).first()
            if curr is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            if curr.crop_version != body.expected_crop_version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_VERSION",
                        "message": "Crop state was replaced during card confirmation.",
                    },
                )
            if curr.search_version != body.expected_search_version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_SEARCH_VERSION",
                        "message": (
                            "Candidate search changed during card confirmation."
                        ),
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_SELECTION_VERSION",
                    "message": "Card selection state changed concurrently.",
                },
            )
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to confirm card for %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to update card confirmation.",
            },
        ) from exc

    db.expire_all()
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    return _build_scan_response(scan)


@router.post("/{id}/reset-card-confirmation", response_model=ScanResponse)
def reset_catalog_card_confirmation(
    id: str,
    body: ResetCardConfirmationRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> ScanResponse:
    """Clear confirmed card selection while keeping confirmed crop intact."""
    response.headers["Cache-Control"] = "no-store"
    scan_id = _validate_uuid(id)
    scan, _ = _get_active_scan(scan_id, db)

    if scan.crop_version != body.expected_crop_version:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_VERSION",
                "message": "The crop state has changed. Please refresh and try again.",
            },
        )

    if (
        body.expected_selection_version is not None
        and scan.card_selection_version != body.expected_selection_version
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "STALE_SELECTION_VERSION",
                "message": "Card confirmation state has changed. Please refresh.",
            },
        )

    now_utc = datetime.now(UTC).replace(tzinfo=None)
    where_clauses = [
        Scan.id == scan_id,
        Scan.crop_version == body.expected_crop_version,
        Scan.expires_at > now_utc,
    ]
    if body.expected_selection_version is not None:
        where_clauses.append(
            Scan.card_selection_version == body.expected_selection_version
        )

    stmt = (
        update(Scan)
        .where(*where_clauses)
        .values(
            confirmed_card_id=None,
            confirmed_card_name=None,
            confirmed_card_set_name=None,
            confirmed_card_number=None,
            confirmed_card_image_url=None,
            card_confirmed_at=None,
            card_selection_version=Scan.card_selection_version + 1,
        )
    )

    try:
        res = db.execute(stmt)
        if res.rowcount == 0:
            db.rollback()
            curr = db.query(Scan).filter(Scan.id == scan_id).first()
            if curr is None:
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_NOT_FOUND", "message": "Scan not found."},
                )
            if curr.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
                raise HTTPException(
                    status_code=404,
                    detail={"code": "SCAN_EXPIRED", "message": "Scan has expired."},
                )
            if curr.crop_version != body.expected_crop_version:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "STALE_VERSION",
                        "message": (
                            "Crop version changed while resetting card confirmation."
                        ),
                    },
                )
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "STALE_SELECTION_VERSION",
                    "message": "Card selection version changed concurrently.",
                },
            )
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("Failed to reset card confirmation for %s", scan_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "DATABASE_ERROR",
                "message": "Failed to reset card confirmation.",
            },
        ) from exc

    db.expire_all()
    scan = db.query(Scan).filter(Scan.id == scan_id).first()
    return _build_scan_response(scan)
