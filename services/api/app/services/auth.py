import base64
import hashlib
import hmac
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.collection import CollectionItem, CollectionScanLink
from app.models.feedback import ScanFeedback
from app.models.scan import Scan
from app.models.scan_session import ScanSession
from app.models.user import User, UserSession

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "dexlens_session"
SESSION_DURATION_DAYS = 30

# Pre-computed dummy Argon2id hash for constant-time dummy verification on
# invalid emails. Salt: 16 null bytes, key: 32 null bytes.
DUMMY_SALT = b"\x00" * 16

DUMMY_SALT_B64 = base64.b64encode(DUMMY_SALT).decode("ascii").rstrip("=")
DUMMY_HASH_B64 = base64.b64encode(b"\x00" * 32).decode("ascii").rstrip("=")
DUMMY_ARGON2_HASH = f"$argon2id$v=19$m=65536,t=3,p=4${DUMMY_SALT_B64}${DUMMY_HASH_B64}"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def hash_password(password: str) -> str:
    """Hash password using Argon2id with RFC 9106 recommended parameters."""
    salt = os.urandom(16)
    kdf = Argon2id(
        salt=salt,
        length=32,
        iterations=3,
        lanes=4,
        memory_cost=65536,
    )
    raw_hash = kdf.derive(password.encode("utf-8"))
    salt_b64 = base64.b64encode(salt).decode("ascii").rstrip("=")
    hash_b64 = base64.b64encode(raw_hash).decode("ascii").rstrip("=")
    return f"$argon2id$v=19$m=65536,t=3,p=4${salt_b64}${hash_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against Argon2id hash."""
    try:
        parts = password_hash.split("$")
        if len(parts) != 6 or parts[1] != "argon2id":
            return False

        # Parse m, t, p parameters
        params = {}
        for item in parts[3].split(","):
            k, v = item.split("=")
            params[k] = int(v)

        m = params.get("m", 65536)
        t = params.get("t", 3)
        p = params.get("p", 4)

        # Pad base64 strings if necessary
        salt_str = parts[4] + "=" * (-len(parts[4]) % 4)
        hash_str = parts[5] + "=" * (-len(parts[5]) % 4)

        salt = base64.b64decode(salt_str)
        expected = base64.b64decode(hash_str)

        kdf = Argon2id(
            salt=salt,
            length=len(expected),
            iterations=t,
            lanes=p,
            memory_cost=m,
        )
        kdf.verify(password.encode("utf-8"), expected)
        return True
    except (InvalidKey, Exception):
        return False


def dummy_verify_password(password: str) -> None:
    """Perform constant-time dummy verification to thwart email enumeration
    timing attacks.
    """
    verify_password(password, DUMMY_ARGON2_HASH)


def hash_token(raw_token: str) -> str:
    """Hash a raw session token using SHA-256 for database lookup."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """Hash client IP using HMAC-SHA256 with PILOT_ADMIN_SECRET for privacy-safe
    anomaly logging.
    """
    if not ip:
        return None
    return hmac.new(
        settings.PILOT_ADMIN_SECRET.encode("utf-8"),
        ip.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def pseudonymize_identifier(identifier: str) -> str:
    """Create a stable, non-reversible identifier for first-party analytics."""
    return hmac.new(
        settings.PILOT_ADMIN_SECRET.encode("utf-8"),
        identifier.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


class EmailAlreadyExistsError(Exception):
    """Raised when registration loses a concurrent unique-email race."""


class AuthService:
    """Service for user authentication, session tokens, and session claiming."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        norm_email = email.strip().lower()
        return self.db.query(User).filter(func.lower(User.email) == norm_email).first()

    def get_user_by_id(self, user_id: str) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def register_user(
        self,
        email: str,
        password: str,
        role: str = "user",
        has_beta_access: bool = False,
        beta_entitlement: str | None = None,
        scan_quota: int | None = None,
        registration_mode_used: str | None = None,
    ) -> User:
        norm_email = email.strip().lower()
        pw_hash = hash_password(password)
        user = User(
            email=norm_email,
            password_hash=pw_hash,
            role=role,
            is_active=True,
            has_beta_access=has_beta_access,
            beta_entitlement=beta_entitlement,
            scan_quota=scan_quota,
            registration_mode_used=registration_mode_used,
        )
        self.db.add(user)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise EmailAlreadyExistsError from exc
        self.db.refresh(user)
        return user

    def register_with_beta_access(
        self,
        email: str,
        password: str,
        beta_code: str | None = None,
        invite_token: str | None = None,
        ip: str | None = None,
        user_agent: str | None = None,
        anonymous_session_id: str | None = None,
    ) -> tuple[User, str]:
        """Atomically register a user with beta-code or invitation redemption.

        Guarantees:
        - If any step fails, the entire transaction is rolled back.
        - No orphan user, session, or redemption record is ever committed.
        - Beta code count is never incremented on failure.
        - Single commit at the very end of the unit of work.
        """
        from app.models.beta_access import BetaCodeRedemption
        from app.services.beta_access import (
            BetaAccessError,
            BetaAccessService,
        )

        norm_email = email.strip().lower()
        if not norm_email or not password:
            raise ValueError("Email and password are required")

        # 1. Check if user already exists
        existing = self.get_user_by_email(norm_email)
        if existing:
            raise EmailAlreadyExistsError("E-mailadres is al in gebruik")

        beta_service = BetaAccessService(self.db)
        active_mode = beta_service.get_registration_mode(self.db)

        try:
            # 2. Lock and consume credential uncommitted
            matched_code, matched_invite, cred_entitlement, cred_quota = (
                beta_service.lock_and_consume_credential(
                    email=norm_email,
                    beta_code_str=beta_code,
                    invite_token_str=invite_token,
                )
            )

            has_beta = (active_mode.value == "open") or bool(
                matched_code or matched_invite
            )
            entitlement = (
                cred_entitlement
                if (matched_code or matched_invite)
                else ("beta" if has_beta else None)
            )
            quota = cred_quota

            # 3. Create user and flush within transaction
            pw_hash = hash_password(password)
            user_id = str(uuid.uuid4())
            user = User(
                id=user_id,
                email=norm_email,
                password_hash=pw_hash,
                role="user",
                is_active=True,
                has_beta_access=has_beta,
                beta_entitlement=entitlement,
                scan_quota=quota,
                registration_mode_used=active_mode.value,
            )
            self.db.add(user)
            self.db.flush()

            # 4. Bind redemption or accepted invitation
            now = _utcnow()
            if matched_code:
                redemption = BetaCodeRedemption(
                    id=str(uuid.uuid4()),
                    beta_code_id=matched_code.id,
                    user_id=user.id,
                    redeemed_at=now,
                    ip_hash=hash_ip(ip),
                    user_agent=user_agent[:255] if user_agent else None,
                )
                self.db.add(redemption)
            elif matched_invite:
                matched_invite.accepted_by_user_id = user.id

            # 5. Claim anonymous session if provided (uncommitted)
            if anonymous_session_id:
                try:
                    self._claim_anonymous_session_uncommitted(
                        user, anonymous_session_id
                    )
                except Exception as exc:
                    logger.warning("Auto-claim during registration failed: %s", exc)

            # 6. Create authenticated session (uncommitted)
            raw_token = secrets.token_urlsafe(32)
            token_hash = hash_token(raw_token)
            expires_at = now + timedelta(days=SESSION_DURATION_DAYS)
            session = UserSession(
                id=str(uuid.uuid4()),
                session_token_hash=token_hash,
                user_id=user.id,
                session_type="authenticated",
                created_at=now,
                expires_at=expires_at,
                ip_hash=hash_ip(ip),
                user_agent=user_agent[:255] if user_agent else None,
            )
            self.db.add(session)

            # 7. Single atomic commit for the entire unit of work
            self.db.commit()
            self.db.refresh(user)
            return user, raw_token

        except IntegrityError as exc:
            self.db.rollback()
            err_msg = (
                str(exc.orig).lower() if hasattr(exc, "orig") else str(exc).lower()
            )
            if (
                "users.email" in err_msg
                or "uq_users_email" in err_msg
                or "email" in err_msg
            ):
                raise EmailAlreadyExistsError("E-mailadres is al in gebruik") from exc
            raise
        except (BetaAccessError, Exception):
            self.db.rollback()
            raise

    def authenticate_user(self, email: str, password: str) -> User | None:
        user = self.get_user_by_email(email)
        if not user or not user.is_active:
            dummy_verify_password(password)
            return None

        if not verify_password(password, user.password_hash):
            return None

        return user

    def create_session(
        self,
        user_id: str | None = None,
        session_type: str = "anonymous",
        ip: str | None = None,
        user_agent: str | None = None,
        duration_days: int = SESSION_DURATION_DAYS,
    ) -> tuple[UserSession, str]:
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        expires_at = _utcnow() + timedelta(days=duration_days)

        now = _utcnow()
        session = UserSession(
            id=str(uuid.uuid4()),
            session_token_hash=token_hash,
            user_id=user_id,
            session_type=session_type,
            created_at=now,
            expires_at=expires_at,
            ip_hash=hash_ip(ip),
            user_agent=user_agent[:255] if user_agent else None,
        )
        self.db.add(session)
        self.db.commit()
        return session, raw_token

    def get_session(self, raw_token: str) -> UserSession | None:
        token_hash = hash_token(raw_token)
        now = _utcnow()
        session = (
            self.db.query(UserSession)
            .filter(
                UserSession.session_token_hash == token_hash,
                UserSession.expires_at > now,
            )
            .first()
        )
        return session

    def invalidate_session(self, raw_token: str) -> bool:
        token_hash = hash_token(raw_token)
        session = (
            self.db.query(UserSession)
            .filter(UserSession.session_token_hash == token_hash)
            .first()
        )
        if session:
            self.db.delete(session)
            self.db.commit()
            return True
        return False

    def _claim_anonymous_session_uncommitted(
        self,
        user: User,
        anonymous_session_id: str,
    ) -> int:
        if not anonymous_session_id:
            return 0

        source_session = (
            self.db.query(UserSession)
            .filter(
                UserSession.id == anonymous_session_id,
                UserSession.user_id.is_(None),
                UserSession.session_type == "anonymous",
                UserSession.expires_at > _utcnow(),
            )
            .first()
        )
        if source_session is None:
            return 0

        claimed_items_count = 0

        # 1. Transfer or merge collection items
        anon_items = (
            self.db.query(CollectionItem)
            .filter(CollectionItem.anonymous_session_id == anonymous_session_id)
            .all()
        )

        for item in anon_items:
            # Check if user already owns an item with the same grouping identity
            existing_user_item = (
                self.db.query(CollectionItem)
                .filter(
                    CollectionItem.user_id == user.id,
                    CollectionItem.provider == item.provider,
                    CollectionItem.card_id == item.card_id,
                    CollectionItem.language == item.language,
                    CollectionItem.variant == item.variant,
                    CollectionItem.condition == item.condition,
                )
                .first()
            )

            if existing_user_item is not None:
                # Merge quantities
                existing_user_item.quantity += item.quantity
                existing_user_item.version += 1
                existing_user_item.updated_at = _utcnow()

                # Re-point scan links from anonymous item to the existing user item
                self.db.query(CollectionScanLink).filter(
                    CollectionScanLink.collection_item_id == item.id
                ).update({"collection_item_id": existing_user_item.id})

                # Delete the redundant anonymous item
                self.db.delete(item)
            else:
                # Transfer ownership
                item.user_id = user.id
                item.anonymous_session_id = None
                item.version += 1
                item.updated_at = _utcnow()

            claimed_items_count += 1

        # 2. Transfer physical scans
        self.db.query(Scan).filter(
            Scan.anonymous_session_id == anonymous_session_id
        ).update(
            {"user_id": user.id, "anonymous_session_id": None},
            synchronize_session=False,
        )

        # 3. Transfer scan sessions
        self.db.query(ScanSession).filter(
            ScanSession.anonymous_session_id == anonymous_session_id
        ).update(
            {"user_id": user.id, "anonymous_session_id": None},
            synchronize_session=False,
        )

        # 4. Transfer scan feedback without violating per-scan/actor uniqueness.
        anonymous_feedback = (
            self.db.query(ScanFeedback)
            .filter(ScanFeedback.anonymous_session_id == anonymous_session_id)
            .all()
        )
        for feedback in anonymous_feedback:
            existing_feedback = (
                self.db.query(ScanFeedback)
                .filter(
                    ScanFeedback.scan_id == feedback.scan_id,
                    ScanFeedback.user_id == user.id,
                )
                .first()
            )
            if existing_feedback:
                self.db.delete(feedback)
            else:
                feedback.user_id = user.id
                feedback.anonymous_session_id = None

        # 5. Expire the anonymous session
        self.db.delete(source_session)

        return claimed_items_count

    def claim_anonymous_session(
        self,
        user: User,
        anonymous_session_id: str,
    ) -> int:
        """Transfer collection items, scans, and sessions from an anonymous
        pilot session to user.
        """
        count = self._claim_anonymous_session_uncommitted(user, anonymous_session_id)
        self.db.commit()
        return count
