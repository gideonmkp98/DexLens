from fastapi import APIRouter, Depends, Request

from app.api.deps import get_audit_service, get_quota_service, require_admin_user
from app.models.user import User
from app.schemas.admin import GlobalQuotaResponse, UpdateGlobalQuotaRequest
from app.services.audit import AuditService
from app.services.quota_service import QuotaServiceInterface

router = APIRouter(prefix="/settings/quota", tags=["Admin Quotas"])


@router.get("", response_model=GlobalQuotaResponse)
def get_global_quota(
    quota_svc: QuotaServiceInterface = Depends(get_quota_service),
    current_admin: User = Depends(require_admin_user),
) -> GlobalQuotaResponse:
    """View global scan quota settings."""
    cfg = quota_svc.get_global_quota()
    return GlobalQuotaResponse(
        daily_scan_limit=cfg.daily_scan_limit,
        hourly_scan_limit=cfg.hourly_scan_limit,
        updated_at=cfg.updated_at,
    )


@router.patch("", response_model=GlobalQuotaResponse)
def update_global_quota(
    payload: UpdateGlobalQuotaRequest,
    request: Request,
    quota_svc: QuotaServiceInterface = Depends(get_quota_service),
    audit_svc: AuditService = Depends(get_audit_service),
    current_admin: User = Depends(require_admin_user),
) -> GlobalQuotaResponse:
    """Update global scan quota settings with confirmation reason and audit logging."""
    old_cfg = quota_svc.get_global_quota()

    updated = quota_svc.update_global_quota(
        daily_limit=payload.daily_scan_limit,
        hourly_limit=payload.hourly_scan_limit,
        actor_id=current_admin.id,
        reason=payload.reason,
    )

    audit_svc.log_action(
        action="quota.update_global",
        target_type="global_settings",
        target_id="scan_quota",
        actor=current_admin,
        metadata={
            "old_daily": old_cfg.daily_scan_limit,
            "new_daily": payload.daily_scan_limit,
            "old_hourly": old_cfg.hourly_scan_limit,
            "new_hourly": payload.hourly_scan_limit,
            "reason": payload.reason,
        },
        request=request,
    )

    return GlobalQuotaResponse(
        daily_scan_limit=updated.daily_scan_limit,
        hourly_scan_limit=updated.hourly_scan_limit,
        updated_at=updated.updated_at,
    )
