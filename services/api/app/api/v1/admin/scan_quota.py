import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_admin_or_pilot_secret
from app.core.database import get_db
from app.models.user import User
from app.schemas.scan_quota import (
    ScanQuotaSettingsResponse,
    ScanQuotaSettingsUpdateRequest,
    UserScanQuotaOverrideRequest,
    UserScanQuotaResponse,
)
from app.services.scan_quota import ScanQuotaService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/scan-quota",
    tags=["Admin Scan Quota"],
    dependencies=[Depends(require_admin_or_pilot_secret)],
)


def _get_quota_service(db: Session = Depends(get_db)) -> ScanQuotaService:
    return ScanQuotaService(db)


def _build_user_quota_response(
    user_id: str,
    service: ScanQuotaService,
) -> UserScanQuotaResponse:
    override = service.get_user_override(user_id)
    override_mode = override.override_mode if override else "inherit"
    custom_limit = override.custom_limit if override else None
    reason = override.reason if override else None
    updated_at = override.updated_at.replace(tzinfo=UTC) if override else None

    quota_status = service.get_quota_status(user_id=user_id, anonymous_session_id=None)

    return UserScanQuotaResponse(
        user_id=user_id,
        override_mode=override_mode,
        custom_limit=custom_limit,
        effective_limit=quota_status.limit,
        used_today=quota_status.used,
        remaining_today=quota_status.remaining,
        reset_at=quota_status.reset_at,
        effective_source=quota_status.effective_source,
        reason=reason,
        updated_at=updated_at,
    )


@router.get("/settings", response_model=ScanQuotaSettingsResponse)
def get_global_scan_quota_settings(
    service: ScanQuotaService = Depends(_get_quota_service),
) -> ScanQuotaSettingsResponse:
    """Retrieve system-wide default daily scan quota settings."""
    limit, updated_at = service.get_global_settings_record()
    return ScanQuotaSettingsResponse(
        default_daily_limit=limit,
        updated_at=updated_at,
    )


@router.put("/settings", response_model=ScanQuotaSettingsResponse)
def update_global_scan_quota_settings(
    body: ScanQuotaSettingsUpdateRequest,
    service: ScanQuotaService = Depends(_get_quota_service),
) -> ScanQuotaSettingsResponse:
    """Update system-wide default daily scan quota limit."""
    limit, updated_at = service.set_global_default_limit(body.default_daily_limit)
    return ScanQuotaSettingsResponse(
        default_daily_limit=limit,
        updated_at=updated_at,
    )


@router.get("/users/{user_id}", response_model=UserScanQuotaResponse)
def get_user_scan_quota(
    user_id: str,
    db: Session = Depends(get_db),
    service: ScanQuotaService = Depends(_get_quota_service),
) -> UserScanQuotaResponse:
    """Retrieve quota override and daily consumption for a specific user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found."},
        )
    return _build_user_quota_response(user_id, service)


@router.put("/users/{user_id}", response_model=UserScanQuotaResponse)
def update_user_scan_quota(
    user_id: str,
    body: UserScanQuotaOverrideRequest,
    db: Session = Depends(get_db),
    service: ScanQuotaService = Depends(_get_quota_service),
) -> UserScanQuotaResponse:
    """Set or update quota override for a specific user."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found."},
        )
    service.set_user_override(
        user_id=user_id,
        override_mode=body.override_mode,
        custom_limit=body.custom_limit,
        reason=body.reason,
    )
    return _build_user_quota_response(user_id, service)


@router.delete("/users/{user_id}", response_model=UserScanQuotaResponse)
def delete_user_scan_quota(
    user_id: str,
    db: Session = Depends(get_db),
    service: ScanQuotaService = Depends(_get_quota_service),
) -> UserScanQuotaResponse:
    """Delete a user quota override, reverting them to inherit global defaults."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "USER_NOT_FOUND", "message": "User not found."},
        )
    service.delete_user_override(user_id)
    return _build_user_quota_response(user_id, service)
