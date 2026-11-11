from fastapi import APIRouter, Depends

from app.api.deps import require_admin_user
from app.core.config import settings
from app.models.user import User
from app.schemas.admin import AbuseStatusResponse

router = APIRouter(prefix="/abuse", tags=["Admin Abuse Protection"])


@router.get("/status", response_model=AbuseStatusResponse)
def get_abuse_status(
    current_admin: User = Depends(require_admin_user),
) -> AbuseStatusResponse:
    """Retrieve active configuration and thresholds for abuse protection."""
    return AbuseStatusResponse(
        turnstile_enabled=settings.TURNSTILE_ENABLED,
        site_key=settings.TURNSTILE_SITE_KEY,
        burst_threshold_anonymous=settings.SCAN_BURST_THRESHOLD,
        burst_threshold_authenticated=settings.SCAN_BURST_THRESHOLD * 4,
        hard_rate_limit=settings.SCAN_HARD_RATE_LIMIT_PER_MINUTE,
    )
