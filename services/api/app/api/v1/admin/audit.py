from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_audit_service, require_admin_user
from app.models.user import User
from app.schemas.admin import AuditLogListResponse, AuditLogResponse
from app.services.audit import AuditService

router = APIRouter(prefix="/audit-logs", tags=["Admin Audit Logs"])


@router.get("", response_model=AuditLogListResponse)
def list_audit_logs(
    action: Annotated[str | None, Query(description="Filter by action")] = None,
    target_type: Annotated[str | None, Query(description="Filter by target type")] = None,
    target_id: Annotated[str | None, Query(description="Filter by target ID")] = None,
    actor_id: Annotated[str | None, Query(description="Filter by actor ID")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    audit_svc: AuditService = Depends(get_audit_service),
    current_admin: User = Depends(require_admin_user),
) -> AuditLogListResponse:
    """View append-only audit trail of administrative operations."""
    items, total = audit_svc.list_logs(
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        limit=limit,
        offset=offset,
    )
    responses = [AuditLogResponse.model_validate(log) for log in items]
    return AuditLogListResponse(items=responses, total=total, limit=limit, offset=offset)
