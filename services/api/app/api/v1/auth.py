import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import SessionContext, get_auth_service, get_session_context
from app.core.config import settings
from app.schemas.auth import (
    AccountMessageResponse,
    ChangeUsernameRequest,
    ClaimAnonymousSessionRequest,
    ClaimAnonymousSessionResponse,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    RequestEmailChangeRequest,
    ResendVerificationRequest,
    UserResponse,
    VerifyEmailRequest,
)
from app.schemas.beta_access import (
    RegistrationMode,
    RegistrationStatusResponse,
    ValidateBetaCodeRequest,
    ValidateBetaCodeResponse,
    ValidateInvitationRequest,
    ValidateInvitationResponse,
)
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_DURATION_DAYS,
    AuthService,
    EmailAlreadyExistsError,
    InvalidPasswordError,
    UsernameAlreadyExistsError,
    UsernameCooldownError,
    dummy_verify_password,
)
from app.services.beta_access import (
    BetaAccessError,
    BetaAccessService,
    mask_email,
)
from app.services.hibp import check_password_pwned
from app.services.turnstile import TurnstileService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/registration-status", response_model=RegistrationStatusResponse)
def get_registration_status(
    auth_service: AuthService = Depends(get_auth_service),
) -> RegistrationStatusResponse:
    """Return active registration mode and requirements for client guidance."""
    mode = BetaAccessService.get_mode(auth_service.db)
    return RegistrationStatusResponse(
        registration_mode=mode.value,
        allows_open_registration=(mode == RegistrationMode.OPEN),
        requires_code_or_invite=(
            mode in (RegistrationMode.BETA_CODE_REQUIRED, RegistrationMode.INVITE_ONLY)
        ),
    )


@router.post("/validate-beta-code", response_model=ValidateBetaCodeResponse)
def validate_beta_code(
    data: ValidateBetaCodeRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> ValidateBetaCodeResponse:
    """Validate a beta code prior to registration form submission."""
    beta_service = BetaAccessService(auth_service.db)
    valid, msg, code = beta_service.validate_beta_code(data.code)
    return ValidateBetaCodeResponse(
        valid=valid,
        label=code.label if code and valid else None,
        message=msg if not valid else None,
    )


@router.post("/validate-invitation", response_model=ValidateInvitationResponse)
def validate_invitation(
    data: ValidateInvitationRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> ValidateInvitationResponse:
    """Validate a personal invitation token prior to registration form submission."""
    beta_service = BetaAccessService(auth_service.db)
    valid, msg, invitation = beta_service.validate_invitation(data.token)
    return ValidateInvitationResponse(
        valid=valid,
        masked_email=mask_email(invitation.email) if invitation and valid else None,
        message=msg if not valid else None,
    )


@router.post(
    "/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED
)
def register(
    data: RegisterRequest,
    response: Response,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse | Response:
    """Register a new collector account with Turnstile protection, modern password
    policy, HIBP checks, atomic beta access controls, and email verification.
    """
    turnstile_token = data.turnstile_token or request.headers.get("x-turnstile-token")
    client_ip = TurnstileService.get_trusted_client_ip(request)
    user_agent = request.headers.get("user-agent")

    is_prod = settings.ENVIRONMENT.lower() in {"production", "prod"}
    force_turnstile = bool(request.headers.get("x-enforce-turnstile"))

    if (
        is_prod
        or settings.TURNSTILE_ENABLED
        or force_turnstile
        or turnstile_token is not None
    ):
        t_result = TurnstileService.verify(
            token=turnstile_token,
            expected_action="register",
            client_ip=client_ip,
        )
        if not t_result.success:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": t_result.error_code or "TURNSTILE_FAILED",
                    "message": t_result.error_message
                    or "Veiligheidscontrole mislukt. Probeer het opnieuw.",
                },
            )

    # 1. Check Have I Been Pwned database using k-anonymity
    is_pwned, breach_count = check_password_pwned(data.password)
    if is_pwned:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "PASSWORD_COMPROMISED",
                "message": (
                    "Dit wachtwoord is voorgekomen in een bekend datalek "
                    "(Have I Been Pwned). Kies een ander, veiliger wachtwoord."
                ),
                "breach_count": breach_count,
            },
        )

    # 2. Check for prior anonymous session to claim
    old_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    old_anon_session_id = None
    if old_cookie:
        old_session = auth_service.get_session(old_cookie)
        if old_session and old_session.session_type == "anonymous":
            old_anon_session_id = old_session.id

    # 3. Check for existing email address
    existing = auth_service.get_user_by_email(data.email)
    if existing:
        dummy_verify_password(data.password)
        if settings.REGISTRATION_NON_ENUMERATION:
            return Response(
                content=json.dumps(
                    {
                        "message": (
                            "Als het account nog niet bestaat, is er een "
                            "verificatielink verstuurd. Controleer je inbox."
                        ),
                        "email_verified": False,
                    }
                ),
                media_type="application/json",
                status_code=status.HTTP_200_OK,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMAIL_ALREADY_EXISTS",
                "message": "E-mailadres is al in gebruik",
            },
        )

    # 4. Check for existing username if provided
    if data.username:
        existing_username = auth_service.get_user_by_username(data.username)
        if existing_username:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "USERNAME_ALREADY_EXISTS",
                    "message": "Deze gebruikersnaam is al in gebruik",
                },
            )

    # 5. Atomically create user account with beta access and session
    try:
        user, raw_token = auth_service.register_with_beta_access(
            email=data.email,
            password=data.password,
            username=data.username,
            accepted_policies=data.accepted_policies,
            beta_code=data.beta_code,
            invite_token=data.invite_token,
            ip=client_ip,
            user_agent=user_agent,
            anonymous_session_id=old_anon_session_id,
        )
    except EmailAlreadyExistsError:
        if settings.REGISTRATION_NON_ENUMERATION:
            return Response(
                content=json.dumps(
                    {
                        "message": (
                            "Als het account nog niet bestaat, is er een "
                            "verificatielink verstuurd. Controleer je inbox."
                        ),
                        "email_verified": False,
                    }
                ),
                media_type="application/json",
                status_code=status.HTTP_200_OK,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMAIL_ALREADY_EXISTS",
                "message": "E-mailadres is al in gebruik",
            },
        ) from None
    except UsernameAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "USERNAME_ALREADY_EXISTS",
                "message": "Deze gebruikersnaam is al in gebruik",
            },
        ) from None
    except BetaAccessError as exc:
        status_code = (
            status.HTTP_403_FORBIDDEN
            if exc.code.startswith("REGISTRATION_")
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from None

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.SECURE_COOKIES,
        max_age=SESSION_DURATION_DAYS * 86400,
        path="/",
    )

    return UserResponse.model_validate(user)


@router.post("/login", response_model=UserResponse)
def login(
    data: LoginRequest,
    response: Response,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Authenticate with email and password and set secure session cookie."""
    user = auth_service.authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_CREDENTIALS",
                "message": "Ongeldige inloggegevens",
            },
        )

    old_cookie = request.cookies.get(SESSION_COOKIE_NAME)
    old_anon_session_id = None
    if old_cookie:
        old_session = auth_service.get_session(old_cookie)
        if old_session and old_session.session_type == "anonymous":
            old_anon_session_id = old_session.id

    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    _, raw_token = auth_service.create_session(
        user_id=user.id,
        session_type="authenticated",
        ip=client_ip,
        user_agent=user_agent,
    )

    if old_anon_session_id:
        try:
            auth_service.claim_anonymous_session(user, old_anon_session_id)
        except Exception as e:
            logger.warning("Auto-claim during login failed: %s", e)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        samesite="lax",
        secure=settings.SECURE_COOKIES,
        max_age=SESSION_DURATION_DAYS * 86400,
        path="/",
    )

    return UserResponse.model_validate(user)


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    """Invalidate current session and delete cookie."""
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        auth_service.invalidate_session(cookie)

    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    return {"message": "Succesvol uitgelogd"}


@router.get("/me", response_model=MeResponse)
def get_me(
    session_ctx: SessionContext = Depends(get_session_context),
) -> MeResponse:
    """Return current user profile or anonymous pilot session identity."""
    user_resp = (
        UserResponse.model_validate(session_ctx.user) if session_ctx.user else None
    )
    return MeResponse(
        is_authenticated=session_ctx.is_authenticated,
        user=user_resp,
        session_id=session_ctx.session_id,
        session_type=session_ctx.session.session_type,
    )


@router.post("/verify-email", response_model=AccountMessageResponse)
@router.get("/verify-email", response_model=AccountMessageResponse)
def verify_email(
    data: VerifyEmailRequest | None = None,
    token: str | None = None,
    auth_service: AuthService = Depends(get_auth_service),
) -> AccountMessageResponse:
    """Verify an email token with single-use semantics."""
    raw_token = data.token if data and data.token else token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "TOKEN_REQUIRED",
                "message": "Verificatietoken is verplicht",
            },
        )

    success, msg, _ = auth_service.verify_email_token(raw_token)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_OR_EXPIRED_TOKEN",
                "message": msg,
            },
        )

    return AccountMessageResponse(message=msg, email_verified=True)


@router.post("/resend-verification", response_model=AccountMessageResponse)
def resend_verification(
    data: ResendVerificationRequest | None = None,
    session_ctx: SessionContext = Depends(get_session_context),
    auth_service: AuthService = Depends(get_auth_service),
) -> AccountMessageResponse:
    """Resend email verification with throttling and non-enumerating responses."""
    target_email = None
    if data and data.email:
        target_email = data.email
    elif session_ctx.user:
        target_email = session_ctx.user.email

    if not target_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "EMAIL_REQUIRED",
                "message": (
                    "E-mailadres is verplicht om een verificatielink te versturen"
                ),
            },
        )

    success, msg, _, remaining = auth_service.resend_verification_token(target_email)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "code": "RESEND_THROTTLED",
                "message": msg,
                "retry_after": remaining,
            },
        )

    return AccountMessageResponse(message=msg)


@router.patch("/username", response_model=UserResponse)
def change_username(
    data: ChangeUsernameRequest,
    session_ctx: SessionContext = Depends(get_session_context),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Change username subject to uniqueness and cooldown period."""
    if not session_ctx.is_authenticated or not session_ctx.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Inloggen vereist om je gebruikersnaam te wijzigen",
            },
        )

    try:
        updated_user = auth_service.change_username(session_ctx.user, data.username)
        return UserResponse.model_validate(updated_user)
    except UsernameAlreadyExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "USERNAME_ALREADY_EXISTS",
                "message": str(exc),
            },
        ) from None
    except UsernameCooldownError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "USERNAME_COOLDOWN",
                "message": str(exc),
            },
        ) from None


@router.post("/email/request-change", response_model=AccountMessageResponse)
def request_email_change(
    data: RequestEmailChangeRequest,
    session_ctx: SessionContext = Depends(get_session_context),
    auth_service: AuthService = Depends(get_auth_service),
) -> AccountMessageResponse:
    """Request an email change with password verification and unverified transition."""
    if not session_ctx.is_authenticated or not session_ctx.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Inloggen vereist om je e-mailadres te wijzigen",
            },
        )

    try:
        _, msg, _ = auth_service.request_email_change(
            session_ctx.user, data.new_email, data.current_password
        )
        return AccountMessageResponse(message=msg)
    except InvalidPasswordError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "INVALID_PASSWORD",
                "message": str(exc),
            },
        ) from None
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "INVALID_EMAIL",
                "message": str(exc),
            },
        ) from None


@router.post("/claim-anonymous-session", response_model=ClaimAnonymousSessionResponse)
def claim_anonymous_session(
    data: ClaimAnonymousSessionRequest,
    session_ctx: SessionContext = Depends(get_session_context),
    auth_service: AuthService = Depends(get_auth_service),
) -> ClaimAnonymousSessionResponse:
    """Claim cards, scans, and scan sessions from an anonymous session
    to the authenticated user.
    """
    if not session_ctx.is_authenticated or not session_ctx.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "UNAUTHENTICATED",
                "message": "Inloggen vereist om data te claimen",
            },
        )

    target_session_id = data.anonymous_session_id
    source_session = auth_service.get_session(data.anonymous_session_token)
    if (
        source_session is None
        or source_session.id != target_session_id
        or source_session.session_type != "anonymous"
        or source_session.user_id is not None
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "INVALID_CLAIM_PROOF",
                "message": "De anonieme sessie kon niet veilig worden geverifieerd",
            },
        )

    claimed_count = auth_service.claim_anonymous_session(
        session_ctx.user,
        target_session_id,
    )

    return ClaimAnonymousSessionResponse(
        claimed_items_count=claimed_count,
        message=f"{claimed_count} item(s) succesvol overgedragen naar je account",
    )
