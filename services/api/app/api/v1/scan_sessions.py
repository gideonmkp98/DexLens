import logging
import uuid
from datetime import UTC, datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from starlette.datastructures import UploadFile as StarletteUploadFile

from app.api.deps import SessionContext, get_session_context
from app.schemas.scan_session import (
    LiveCaptureResponse,
    ScanSessionCreateRequest,
    ScanSessionDetailResponse,
    ScanSessionResponse,
)
from app.services.abuse import ScanAbuseService
from app.services.scan_session import (
    ScanSessionError,
    ScanSessionService,
    get_scan_session_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan-sessions", tags=["Scan Sessions"])


def _validate_uuid(val: str) -> str:
    """Validate that val is a valid UUID string to prevent path traversal."""
    try:
        parsed = uuid.UUID(val)
        return str(parsed)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SESSION_NOT_FOUND", "message": "Scan session not found."},
        ) from None


@router.post(
    "",
    response_model=ScanSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    body: ScanSessionCreateRequest | None = None,
    service: ScanSessionService = Depends(get_scan_session_service),
) -> ScanSessionResponse:
    """Create a new active scan session for continuous card scanning."""
    try:
        return service.create_session()
    except ScanSessionError as err:
        raise HTTPException(
            status_code=err.status_code,
            detail={"code": err.code, "message": err.message},
        ) from err


@router.get(
    "/{id}",
    response_model=ScanSessionDetailResponse,
    status_code=status.HTTP_200_OK,
)
async def get_session(
    id: str,
    response: Response,
    service: ScanSessionService = Depends(get_scan_session_service),
) -> ScanSessionDetailResponse:
    """Retrieve scan session details and ordered list of scanned cards."""
    response.headers["Cache-Control"] = "no-store"
    session_id = _validate_uuid(id)
    try:
        return await service.get_session(session_id)
    except ScanSessionError as err:
        raise HTTPException(
            status_code=err.status_code,
            detail={"code": err.code, "message": err.message},
        ) from err


@router.post(
    "/{id}/capture",
    response_model=LiveCaptureResponse,
    status_code=status.HTTP_200_OK,
)
async def capture_frame(
    id: str,
    request: Request,
    response: Response,
    file: UploadFile = File(
        ...,
        description="Camera frame image for live card detection and recognition",
    ),
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
        min_length=8,
        max_length=64,
        pattern=r"^[A-Za-z0-9._:-]+$",
    ),
    service: ScanSessionService = Depends(get_scan_session_service),
    session_ctx: SessionContext = Depends(get_session_context),
) -> LiveCaptureResponse:
    """Live frame capture: detects card bounds and runs recognition."""
    response.headers["Cache-Control"] = "no-store"
    session_id = _validate_uuid(id)

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

    # Adaptive abuse protection check
    raw_turnstile = request.headers.get("x-turnstile-token") or form.get(
        "turnstile_token"
    )
    turnstile_token = str(raw_turnstile).strip() if raw_turnstile else None

    ScanAbuseService.check_scan_permission(
        request=request,
        user_id=session_ctx.user_id,
        turnstile_token=turnstile_token,
    )

    try:
        result = await service.capture_frame(
            session_id=session_id,
            image_input=file,
            idempotency_key=idempotency_key,
        )
        if result.scan.quota is not None:
            response.headers["X-Quota-Limit"] = (
                str(result.scan.quota.limit)
                if result.scan.quota.limit is not None
                else "unlimited"
            )
            response.headers["X-Quota-Used"] = str(result.scan.quota.used)
            response.headers["X-Quota-Remaining"] = (
                str(result.scan.quota.remaining)
                if result.scan.quota.remaining is not None
                else "unlimited"
            )
            response.headers["X-Quota-Reset"] = result.scan.quota.reset_at.isoformat()
            response.headers["X-Quota-Source"] = result.scan.quota.effective_source
        return result
    except ScanSessionError as err:
        headers = {}
        if err.quota is not None:
            reset_secs = max(
                0, int((err.quota.reset_at - datetime.now(UTC)).total_seconds())
            )
            headers = {
                "Retry-After": str(reset_secs),
                "X-Quota-Limit": str(err.quota.limit)
                if err.quota.limit is not None
                else "unlimited",
                "X-Quota-Used": str(err.quota.used),
                "X-Quota-Remaining": str(err.quota.remaining)
                if err.quota.remaining is not None
                else "unlimited",
                "X-Quota-Reset": err.quota.reset_at.isoformat(),
                "X-Quota-Source": err.quota.effective_source,
            }
        detail = {"code": err.code, "message": err.message}
        if err.quota is not None:
            detail["quota"] = err.quota.model_dump(mode="json")
        raise HTTPException(
            status_code=err.status_code,
            detail=detail,
            headers=headers,
        ) from err

    # Record scan activity only after successful capture/processing
    ScanAbuseService.record_scan_activity(
        request=request,
        user_id=session_ctx.user_id,
    )

    return result


@router.post(
    "/{id}/complete",
    response_model=ScanSessionResponse,
    status_code=status.HTTP_200_OK,
)
def complete_session(
    id: str,
    response: Response,
    service: ScanSessionService = Depends(get_scan_session_service),
) -> ScanSessionResponse:
    """Mark an active scan session as completed."""
    response.headers["Cache-Control"] = "no-store"
    session_id = _validate_uuid(id)
    try:
        return service.complete_session(session_id)
    except ScanSessionError as err:
        raise HTTPException(
            status_code=err.status_code,
            detail={"code": err.code, "message": err.message},
        ) from err
