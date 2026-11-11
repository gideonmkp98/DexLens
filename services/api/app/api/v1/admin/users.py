from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from app.api.deps import get_admin_service, require_admin_user
from app.models.user import User
from app.schemas.admin import (
    AdminUserDetailsResponse,
    AdminUserItem,
    AdminUserListResponse,
    UpdateUserQuotaRequest,
    UpdateUserStatusRequest,
)
from app.services.admin import AdminService

router = APIRouter(prefix="/users", tags=["Admin Users"])


@router.get("", response_model=AdminUserListResponse)
def list_users(
    q: Annotated[str | None, Query(description="Search email or ID")] = None,
    status: Annotated[str | None, Query(description="Status filter")] = None,
    role: Annotated[str | None, Query(description="Role filter")] = None,
    verification_status: Annotated[
        str | None, Query(description="Verification status")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    service: AdminService = Depends(get_admin_service),
    current_admin: User = Depends(require_admin_user),
) -> AdminUserListResponse:
    """Lookup and filter collector accounts."""
    users, total = service.list_users(
        q=q,
        status_filter=status,
        role_filter=role,
        verification_filter=verification_status,
        limit=limit,
        offset=offset,
    )
    items = [AdminUserItem.model_validate(u) for u in users]
    return AdminUserListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/{id}", response_model=AdminUserDetailsResponse)
def get_user_details(
    id: str,
    service: AdminService = Depends(get_admin_service),
    current_admin: User = Depends(require_admin_user),
) -> AdminUserDetailsResponse:
    """Retrieve detailed user account status, quotas, and recent activity."""
    details = service.get_user_details(id)
    return AdminUserDetailsResponse(**details)


@router.patch("/{id}/status", response_model=AdminUserItem)
def update_user_status(
    id: str,
    payload: UpdateUserStatusRequest,
    request: Request,
    service: AdminService = Depends(get_admin_service),
    current_admin: User = Depends(require_admin_user),
) -> AdminUserItem:
    """Activate, suspend, or block user with reason confirmation and audit log."""
    updated_user = service.update_user_status(
        user_id=id,
        new_status=payload.status,
        reason=payload.reason,
        actor=current_admin,
        request=request,
    )
    return AdminUserItem.model_validate(updated_user)


@router.patch("/{id}/quota", response_model=AdminUserItem)
def update_user_quota(
    id: str,
    payload: UpdateUserQuotaRequest,
    request: Request,
    service: AdminService = Depends(get_admin_service),
    current_admin: User = Depends(require_admin_user),
) -> AdminUserItem:
    """Change per-user scan quota override."""
    updated_user = service.update_user_quota_override(
        user_id=id,
        custom_limit=payload.scan_quota_override,
        reason=payload.reason,
        actor=current_admin,
        request=request,
    )
    return AdminUserItem.model_validate(updated_user)
