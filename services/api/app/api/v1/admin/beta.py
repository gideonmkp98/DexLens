from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_audit_service, get_beta_service, require_admin_user
from app.models.user import User
from app.schemas.admin import (
    BetaCodeListResponse,
    BetaCodeResponse,
    CreateBetaCodeRequest,
    RevokeBetaCodeRequest,
)
from app.services.audit import AuditService
from app.services.beta_service import BetaServiceInterface

router = APIRouter(prefix="/beta/codes", tags=["Admin Beta Codes"])


@router.get("", response_model=BetaCodeListResponse)
def list_beta_codes(
    status: Annotated[str | None, Query(description="Status filter")] = None,
    search: Annotated[str | None, Query(description="Search label or code")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    beta_svc: BetaServiceInterface = Depends(get_beta_service),
    current_admin: User = Depends(require_admin_user),
) -> BetaCodeListResponse:
    """List and filter beta codes and invitations."""
    items, total = beta_svc.list_codes(
        status=status,
        search=search,
        limit=limit,
        offset=offset,
    )
    responses = [
        BetaCodeResponse(
            id=i.id,
            code=i.code,
            code_prefix=i.code_prefix,
            label=i.label,
            invitation_email=i.invitation_email,
            max_uses=i.max_uses,
            used_count=i.used_count,
            status=i.status,
            expires_at=i.expires_at,
            created_at=i.created_at,
            created_by_user_id=i.created_by_user_id,
        )
        for i in items
    ]
    return BetaCodeListResponse(
        items=responses, total=total, limit=limit, offset=offset
    )


@router.post("", response_model=BetaCodeResponse)
def create_beta_code(
    payload: CreateBetaCodeRequest,
    request: Request,
    beta_svc: BetaServiceInterface = Depends(get_beta_service),
    audit_svc: AuditService = Depends(get_audit_service),
    current_admin: User = Depends(require_admin_user),
) -> BetaCodeResponse:
    """Create a new beta invitation code with audit trail."""
    expires_at = None
    if payload.expires_days:
        expires_at = datetime.now(UTC).replace(tzinfo=None) + timedelta(
            days=payload.expires_days
        )

    code_item = beta_svc.create_code(
        code=payload.code,
        label=payload.label,
        invitation_email=payload.invitation_email,
        max_uses=payload.max_uses,
        expires_at=expires_at,
        created_by_id=current_admin.id,
    )

    audit_svc.log_action(
        action="beta.create_code",
        target_type="beta_code",
        target_id=code_item.id,
        actor=current_admin,
        metadata={
            "code_prefix": code_item.code_prefix,
            "max_uses": payload.max_uses,
            "invitation_email": payload.invitation_email,
        },
        request=request,
    )

    return BetaCodeResponse(
        id=code_item.id,
        code=code_item.code,
        code_prefix=code_item.code_prefix,
        label=code_item.label,
        invitation_email=code_item.invitation_email,
        max_uses=code_item.max_uses,
        used_count=code_item.used_count,
        status=code_item.status,
        expires_at=code_item.expires_at,
        created_at=code_item.created_at,
        created_by_user_id=code_item.created_by_user_id,
    )


@router.patch("/{code_or_id}/revoke", response_model=BetaCodeResponse)
def revoke_beta_code(
    code_or_id: str,
    payload: RevokeBetaCodeRequest,
    request: Request,
    beta_svc: BetaServiceInterface = Depends(get_beta_service),
    audit_svc: AuditService = Depends(get_audit_service),
    current_admin: User = Depends(require_admin_user),
) -> BetaCodeResponse:
    """Revoke an active beta code with confirmation reason and audit log."""
    revoked_item = beta_svc.revoke_code(
        code_or_id=code_or_id,
        actor_id=current_admin.id,
        reason=payload.reason,
    )

    audit_svc.log_action(
        action="beta.revoke_code",
        target_type="beta_code",
        target_id=revoked_item.id,
        actor=current_admin,
        metadata={
            "code_prefix": revoked_item.code_prefix,
            "reason": payload.reason,
        },
        request=request,
    )

    return BetaCodeResponse(
        id=revoked_item.id,
        code=revoked_item.code,
        code_prefix=revoked_item.code_prefix,
        label=revoked_item.label,
        invitation_email=revoked_item.invitation_email,
        max_uses=revoked_item.max_uses,
        used_count=revoked_item.used_count,
        status=revoked_item.status,
        expires_at=revoked_item.expires_at,
        created_at=revoked_item.created_at,
        created_by_user_id=revoked_item.created_by_user_id,
    )
