import logging
import uuid

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
        uuid_obj = uuid.UUID(val)
        return str(uuid_obj)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_UUID", "message": f"Invalid UUID: '{val}'"},
        )


@router.get("", response_model=list[ScanSessionResponse])
def list_sessions(
    service: ScanSessionService = Depends(get_scan_session_service),
) -> list[ScanSessionResponse]:
    """List recent scan sessions."""
    return service.list_sessions()


@router.post(
    "",
    response_model=ScanSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_session(
    body: ScanSessionCreateRequest | None = None,
    service: ScanSessionService = Depends(get_scan_session_service),
) -> ScanSessionResponse:
    """Initialize a new scanning session."""
    device_info = body.device_info if body else None
    return service.create_session(device_info=device_info)


@router.get(
    "/{id}",
    response_model=ScanSessionDetailResponse,
    status_code=status.HTTP_200_OK,
)
def get_session(
    id: str,
    service: ScanSessionService = Depends(get_scan_session_service),
) -> ScanSessionDetailResponse:
    """Get active session state with all associated scans."""
    session_id = _validate_uuid(id)
    try:
        return service.get_session(session_id)
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
    raw_turnstile = request.headers.get("x-turnstile-token") or form.get("turnstile_token")
    turnstile_token = str(raw_turnstile).strip() if raw_turnstile else None

    from app.services.abuse import ScanAbuseService

    ScanAbuseService.check_and_record_scan(
        request=request,
        user_id=session_ctx.user_id,
        turnstile_token=turnstile_token,
    )

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

    try:
        return await service.capture_frame(
            session_id=session_id,
            image_input=file,
            idempotency_key=idempotency_key,
        )
    except ScanSessionError as err:
        raise HTTPException(
            status_code=err.status_code,
            detail={"code": err.code, "message": err.message},
        ) from err


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
