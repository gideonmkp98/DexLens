import logging
import uuid

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
from starlette.datastructures import UploadFile as StarletteUploadFile

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
        parsed = uuid.UUID(val)
        return str(parsed)
    except ValueError:
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
    service: ScanSessionService = Depends(get_scan_session_service),
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

    try:
        return await service.capture_frame(session_id=session_id, image_input=file)
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
