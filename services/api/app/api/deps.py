import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User, UserSession
from app.services.auth import (
    SESSION_COOKIE_NAME,
    SESSION_DURATION_DAYS,
    AuthService,
)

logger = logging.getLogger(__name__)


class SessionContext:
    """Encapsulates the resolved session and user context for the active request."""

    def __init__(
        self,
        session: UserSession,
        user: User | None = None,
        is_new: bool = False,
        raw_token: str | None = None,
    ) -> None:
        self.session = session
        self.user = user
        self.is_new = is_new
        self.raw_token = raw_token

    @property
    def session_id(self) -> str:
        return self.session.id

    @property
    def user_id(self) -> str | None:
        return self.user.id if self.user else None

    @property
    def anonymous_session_id(self) -> str | None:
        return self.session.id if not self.user else None

    @property
    def is_authenticated(self) -> bool:
        return self.user is not None


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_session_context(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> SessionContext:
    """Resolve or auto-provision session context for the request.

    If no valid session cookie is present, an anonymous pilot session is created
    and the HttpOnly session cookie is attached to the response.
    """
    auth_service = AuthService(db)

    # 1. Look for cookie token or Bearer authorization header
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_token = auth_header.split(" ", 1)[1].strip()

    if raw_token:
        session = auth_service.get_session(raw_token)
        if session:
            user = None
            if session.user_id:
                user = auth_service.get_user_by_id(session.user_id)
                if not user or not user.is_active:
                    user = None
            return SessionContext(session=session, user=user)

    # 2. Auto-provision anonymous pilot session
    client_ip = None
    if request.client:
        client_ip = request.client.host
    user_agent = request.headers.get("user-agent")

    try:
        session, new_token = auth_service.create_session(
            user_id=None,
            session_type="anonymous",
            ip=client_ip,
            user_agent=user_agent,
        )

        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=new_token,
            httponly=True,
            samesite="lax",
            secure=settings.SECURE_COOKIES,
            max_age=SESSION_DURATION_DAYS * 86400,
            path="/",
        )

        return SessionContext(
            session=session,
            user=None,
            is_new=True,
            raw_token=new_token,
        )
    except Exception as exc:
        logger.warning("Could not persist anonymous session in DB: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        fallback_session = UserSession(
            id=str(uuid.uuid4()),
            user_id=None,
            session_token_hash="",
            session_type="anonymous",
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        return SessionContext(
            session=fallback_session,
            user=None,
            is_new=False,
            raw_token="",
        )


def require_authenticated_user(
    session_ctx: SessionContext = Depends(get_session_context),
) -> User:
    """Require an authenticated user account."""
    if not session_ctx.is_authenticated or not session_ctx.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHENTICATED", "message": "Inloggen vereist"},
        )
    return session_ctx.user


def require_admin_or_pilot_secret(
    request: Request,
    x_pilot_admin_token: Annotated[str | None, Header()] = None,
    session_ctx: SessionContext = Depends(get_session_context),
) -> bool:
    """Verify admin privileges via token header or authenticated admin user session."""
    # Check X-Pilot-Admin-Token
    if x_pilot_admin_token and secrets.compare_digest(
        x_pilot_admin_token, settings.PILOT_ADMIN_SECRET
    ):
        return True

    # Check Authorization: Bearer <secret>
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if secrets.compare_digest(token, settings.PILOT_ADMIN_SECRET):
            return True

    # Check session user role
    if session_ctx.user and session_ctx.user.role in ("admin", "pilot"):
        return True

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={"code": "FORBIDDEN", "message": "Pilot admin access required"},
    )
