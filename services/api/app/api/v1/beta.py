from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.api.deps import SessionContext, get_beta_service, get_session_context
from app.services.auth import hash_ip
from app.services.beta_service import BetaServiceInterface
from app.services.turnstile import TurnstileService

router = APIRouter(prefix="/beta", tags=["Beta"])


class ClaimBetaCodeRequest(BaseModel):
    code: str
    turnstile_token: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        clean = v.strip().upper()
        if len(clean) < 4:
            raise ValueError("Beta-code is te kort.")
        return clean


class ClaimBetaCodeResponse(BaseModel):
    success: bool
    message: str


@router.post("/claim", response_model=ClaimBetaCodeResponse)
def claim_beta_code(
    payload: ClaimBetaCodeRequest,
    request: Request,
    x_turnstile_token: Annotated[str | None, Header(alias="X-Turnstile-Token")] = None,
    session_ctx: SessionContext = Depends(get_session_context),
    beta_svc: BetaServiceInterface = Depends(get_beta_service),
) -> ClaimBetaCodeResponse:
    """Complete and claim a beta code with mandatory Turnstile abuse protection."""
    token = payload.turnstile_token or x_turnstile_token
    client_ip = TurnstileService.get_trusted_client_ip(request)

    turnstile_result = TurnstileService.verify(
        token=token,
        expected_action="invite_completion",
        client_ip=client_ip,
    )
    if not turnstile_result.success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": turnstile_result.error_code or "TURNSTILE_FAILED",
                "message": turnstile_result.error_message or "Veiligheidscontrole mislukt.",
            },
        )

    user_id = session_ctx.user_id or session_ctx.session_id
    claimed = beta_svc.claim_code(
        code=payload.code,
        user_id=user_id,
        ip_hash=hash_ip(client_ip),
    )
    if not claimed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_OR_EXHAUSTED_BETA_CODE",
                "message": "Ongeldige, verlopen of reeds uitgeputte beta-code.",
            },
        )

    return ClaimBetaCodeResponse(
        success=True,
        message="Beta-code succesvol geactiveerd!",
    )
