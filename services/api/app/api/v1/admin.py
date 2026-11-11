import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import (
    SessionContext,
    get_db,
    get_session_context,
    require_admin_or_pilot_secret,
)
from app.schemas.beta_access import (
    BetaCodeCreatedResponse,
    BetaCodeDetailResponse,
    BetaCodeRedemptionResponse,
    BetaCodeResponse,
    CreateBetaCodeRequest,
    CreateInvitationRequest,
    InvitationResponse,
    UpdateRegistrationModeRequest,
)
from app.services.beta_access import (
    BetaAccessError,
    BetaAccessService,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin_or_pilot_secret)],
)


# --- Registration Mode Management ---


@router.get("/registration-mode")
def get_registration_mode() -> dict[str, str]:
    """Get the active registration mode."""
    mode = BetaAccessService.get_registration_mode()
    return {"registration_mode": mode.value}


@router.put("/registration-mode")
def update_registration_mode(
    data: UpdateRegistrationModeRequest,
) -> dict[str, str]:
    """Update the server-wide active registration mode."""
    BetaAccessService.set_registration_mode(data.registration_mode)
    return {
        "registration_mode": data.registration_mode.value,
        "message": f"Registratiemodus bijgewerkt naar {data.registration_mode.value}",
    }


# --- Beta Code Management ---


@router.post(
    "/beta-codes",
    response_model=BetaCodeCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_beta_code(
    data: CreateBetaCodeRequest,
    db: Session = Depends(get_db),
    session_ctx: SessionContext = Depends(get_session_context),
) -> BetaCodeCreatedResponse:
    """Create a new beta code.

    Returns the full plaintext code once upon creation.
    The code secret is hashed for storage and never exposed again.
    """
    service = BetaAccessService(db)
    creator_id = session_ctx.user_id
    try:
        code_obj, raw_code = service.create_beta_code(
            label=data.label,
            max_uses=data.max_uses,
            expires_at=data.expires_at,
            allowed_email=data.allowed_email,
            scan_quota_allocated=data.scan_quota_allocated,
            beta_entitlement=data.beta_entitlement,
            custom_code=data.custom_code,
            created_by_user_id=creator_id,
        )
    except BetaAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from None

    return BetaCodeCreatedResponse(
        id=code_obj.id,
        code=raw_code,
        code_prefix=code_obj.code_prefix,
        label=code_obj.label,
        is_active=code_obj.is_active,
        max_uses=code_obj.max_uses,
        used_count=code_obj.used_count,
        allowed_email=code_obj.allowed_email,
        scan_quota_allocated=code_obj.scan_quota_allocated,
        beta_entitlement=code_obj.beta_entitlement,
        expires_at=code_obj.expires_at,
        created_at=code_obj.created_at,
    )


@router.get("/beta-codes")
def list_beta_codes(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    active_only: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List beta codes with pagination. Tokens/codes are masked."""
    service = BetaAccessService(db)
    items, total = service.list_beta_codes(
        skip=skip, limit=limit, active_only=active_only
    )
    return {
        "items": [BetaCodeResponse.model_validate(item) for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/beta-codes/{code_id}", response_model=BetaCodeDetailResponse)
def get_beta_code_detail(
    code_id: str,
    db: Session = Depends(get_db),
) -> BetaCodeDetailResponse:
    """Retrieve details and redemption audit history for a beta code."""
    service = BetaAccessService(db)
    code_obj = service.get_beta_code_by_id(code_id)
    if not code_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Bètacode niet gevonden"},
        )

    redemptions = [
        BetaCodeRedemptionResponse.model_validate(r) for r in code_obj.redemptions
    ]
    resp = BetaCodeDetailResponse.model_validate(code_obj)
    resp.redemptions = redemptions
    return resp


@router.post("/beta-codes/{code_id}/revoke", response_model=BetaCodeResponse)
def revoke_beta_code(
    code_id: str,
    db: Session = Depends(get_db),
    session_ctx: SessionContext = Depends(get_session_context),
) -> BetaCodeResponse:
    """Revoke an active beta code immediately."""
    service = BetaAccessService(db)
    try:
        code_obj = service.revoke_beta_code(
            code_id=code_id,
            revoked_by_user_id=session_ctx.user_id,
        )
    except BetaAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from None
    return BetaCodeResponse.model_validate(code_obj)


# --- Invitation Management ---


@router.post(
    "/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    data: CreateInvitationRequest,
    db: Session = Depends(get_db),
    session_ctx: SessionContext = Depends(get_session_context),
) -> InvitationResponse:
    """Generate and dispatch a personal email invitation.

    The secret token is dispatched directly to recipient email and is never
    returned in API responses or plain DB records.
    """
    service = BetaAccessService(db)
    try:
        invitation, _ = service.create_invitation(
            email=data.email,
            expires_in_days=data.expires_in_days,
            scan_quota_allocated=data.scan_quota_allocated,
            beta_entitlement=data.beta_entitlement,
            created_by_user_id=session_ctx.user_id,
        )
    except BetaAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from None
    return InvitationResponse.model_validate(invitation)


@router.get("/invitations")
def list_invitations(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """List invitations with pagination. Tokens are strictly excluded."""
    service = BetaAccessService(db)
    items, total = service.list_invitations(
        skip=skip, limit=limit, status_filter=status_filter
    )
    return {
        "items": [InvitationResponse.model_validate(item) for item in items],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/invitations/{invite_id}", response_model=InvitationResponse)
def get_invitation_detail(
    invite_id: str,
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """Get single invitation status."""
    service = BetaAccessService(db)
    invitation = service.get_invitation_by_id(invite_id)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOT_FOUND", "message": "Uitnodiging niet gevonden"},
        )
    return InvitationResponse.model_validate(invitation)


@router.post("/invitations/{invite_id}/revoke", response_model=InvitationResponse)
def revoke_invitation(
    invite_id: str,
    db: Session = Depends(get_db),
    session_ctx: SessionContext = Depends(get_session_context),
) -> InvitationResponse:
    """Revoke a pending invitation."""
    service = BetaAccessService(db)
    try:
        invitation = service.revoke_invitation(
            invite_id=invite_id,
            revoked_by_user_id=session_ctx.user_id,
        )
    except BetaAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from None
    return InvitationResponse.model_validate(invitation)


@router.post("/invitations/{invite_id}/resend", response_model=InvitationResponse)
def resend_invitation(
    invite_id: str,
    db: Session = Depends(get_db),
) -> InvitationResponse:
    """Resend invitation with a newly generated token, invalidating prior token."""
    service = BetaAccessService(db)
    try:
        invitation, _ = service.resend_invitation(invite_id=invite_id)
    except BetaAccessError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": exc.code, "message": exc.message},
        ) from None
    return InvitationResponse.model_validate(invitation)
