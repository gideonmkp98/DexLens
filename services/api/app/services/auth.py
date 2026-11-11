import base64
import hashlib
import hmac
import logging
import os
import re
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
from app.models.user import EmailVerification, User, UserSession

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
    derived = kdf.derive(password.encode("utf-8"))
    salt_b64 = base64.b64encode(salt).decode("ascii").rstrip("=")
    hash_b64 = base64.b64encode(derived).decode("ascii").rstrip("=")
    return f"$argon2id$v=19$m=65536,t=3,p=4${salt_b64}${hash_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    """Verify password against Argon2id hash in constant time."""
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
    """Hash a raw session or verification token using SHA-256 for database lookup."""
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


def generate_default_username(email: str, db: Session) -> str:
    """Generate a clean, unique default username from an email address."""
    base = re.sub(r"[^a-z0-9_-]", "", email.split("@")[0].lower())[:20]
    if len(base) < 3:
        base = "collector"
    candidate = base
    suffix_len = 4
    while True:
        existing = (
            db.query(User)
            .filter(func.lower(User.username) == candidate.lower())
            .first()
        )
        if not existing:
            return candidate
        candidate = f"{base[:15]}_{secrets.token_hex(suffix_len // 2)}"
        suffix_len += 2


class EmailAlreadyExistsError(Exception):
    """Raised when registration loses a concurrent unique-email race."""


class UsernameAlreadyExistsError(Exception):
    """Raised when registration or update loses a concurrent unique-username race."""


class UsernameCooldownError(Exception):
    """Raised when username change is requested before cooldown expires."""


class InvalidPasswordError(Exception):
    """Raised when password verification fails during sensitive actions."""


class AuthService:
    """Service for user authentication, session tokens, and session claiming."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_user_by_email(self, email: str) -> User | None:
        norm_email = email.strip().lower()
        return self.db.query(User).filter(func.lower(User.email) == norm_email).first()

    def get_user_by_username(self, username: str) -> User | None:
        norm_username = username.strip().lower()
        return (
            self.db.query(User)
            .filter(func.lower(User.username) == norm_username)
            .first()
        )

    def get_user_by_id(self, user_id: str) -> User | None:
        return self.db.query(User).filter(User.id == user_id).first()

    def register_user(
        self,
        email: str,
        password: str,
        username: str | None = None,
        role: str = "user",
        accepted_policies: bool = True,
    ) -> tuple[User, str]:
        """Register a new collector account with normalized credentials and
        initial email verification token.
        """
        norm_email = email.strip().lower()
        if username:
            norm_username = username.strip().lower()
            if self.get_user_by_username(norm_username):
                raise UsernameAlreadyExistsError("Deze gebruikersnaam is al in gebruik")
        else:
            norm_username = generate_default_username(norm_email, self.db)

        pw_hash = hash_password(password)
        now = _utcnow()
        user = User(
            email=norm_email,
            username=norm_username,
            password_hash=pw_hash,
            role=role,
            is_active=True,
            email_verified=False,
            policies_accepted_at=now if accepted_policies else None,
        )
        self.db.add(user)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            if self.get_user_by_email(norm_email):
                raise EmailAlreadyExistsError from exc
            if self.get_user_by_username(norm_username):
                raise UsernameAlreadyExistsError from exc
            raise EmailAlreadyExistsError from exc

        # Create initial email verification token
        raw_verification_token = secrets.token_urlsafe(32)
        verification = EmailVerification(
            id=str(uuid.uuid4()),
            user_id=user.id,
            token_hash=hash_token(raw_verification_token),
            token_type="email_verification",
            expires_at=now + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS),
            created_at=now,
        )
        self.db.add(verification)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise EmailAlreadyExistsError from exc

        self.db.refresh(user)
        logger.info(
            "Registered user %s (%s). Verification token generated.",
            user.email,
            user.username,
        )
        return user, raw_verification_token

    def create_email_verification(
        self,
        user_id: str,
        token_type: str = "email_verification",
        target_email: str | None = None,
    ) -> tuple[EmailVerification, str]:
        """Create a secure, hashed single-use email verification token."""
        raw_token = secrets.token_urlsafe(32)
        token_hash = hash_token(raw_token)
        now = _utcnow()
        expires_at = now + timedelta(hours=settings.EMAIL_VERIFICATION_EXPIRE_HOURS)

        verification = EmailVerification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            token_hash=token_hash,
            token_type=token_type,
            target_email=target_email.strip().lower() if target_email else None,
            expires_at=expires_at,
            created_at=now,
        )
        self.db.add(verification)
        self.db.commit()
        self.db.refresh(verification)
        return verification, raw_token

    def verify_email_token(self, raw_token: str) -> tuple[bool, str, User | None]:
        """Verify an email token with single-use semantics and expiration checking."""
        token_hash = hash_token(raw_token)
        now = _utcnow()
        verification = (
            self.db.query(EmailVerification)
            .filter(
                EmailVerification.token_hash == token_hash,
                EmailVerification.used_at.is_(None),
                EmailVerification.expires_at > now,
            )
            .first()
        )
        if verification is None:
            return False, "Verificatielink is ongeldig of verlopen", None

        user = self.get_user_by_id(verification.user_id)
        if user is None:
            return False, "Verificatielink is ongeldig of verlopen", None

        # Mark single-use consumption
        verification.used_at = now

        if verification.token_type == "email_change":
            if not verification.target_email:
                return False, "Ongeldige verificatieaanvraag", None
            existing = self.get_user_by_email(verification.target_email)
            if existing and existing.id != user.id:
                return (
                    False,
                    "E-mailadres is inmiddels al in gebruik door een ander account",
                    None,
                )
            user.email = verification.target_email
            user.email_verified = True
        else:
            user.email_verified = True

        self.db.commit()
        self.db.refresh(user)
        return True, "E-mailadres succesvol geverifieerd", user

    def resend_verification_token(
        self, email: str
    ) -> tuple[bool, str, str | None, int | None]:
        """Resend verification email with throttling and non-enumerating responses."""
        norm_email = email.strip().lower()
        user = self.get_user_by_email(norm_email)

        # Non-enumeration: uniform response if user does not exist or already verified
        msg = (
            "Als het e-mailadres bij ons bekend is en nog niet is geverifieerd, "
            "hebben we een nieuwe verificatielink verzonden."
        )
        if user is None or user.email_verified:
            return (True, msg, None, None)

        now = _utcnow()
        # Throttling check
        recent = (
            self.db.query(EmailVerification)
            .filter(
                EmailVerification.user_id == user.id,
                EmailVerification.token_type == "email_verification",
            )
            .order_by(EmailVerification.created_at.desc())
            .first()
        )
        if recent is not None:
            elapsed = (now - recent.created_at).total_seconds()
            if elapsed < settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS:
                remaining = int(
                    settings.EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS - elapsed
                )
                return (
                    False,
                    f"Wacht {remaining} seconden voordat je een nieuwe "
                    "verificatielink aanvraagt.",
                    None,
                    remaining,
                )

        _, raw_token = self.create_email_verification(
            user_id=user.id, token_type="email_verification"
        )
        logger.info("Resent verification token for %s: %s", user.email, raw_token)
        return (True, msg, raw_token, None)

    def change_username(self, user: User, new_username: str) -> User:
        """Change username subject to uniqueness and a 30-day cooldown period."""
        norm = new_username.strip().lower()
        if user.username and norm == user.username.lower():
            return user

        existing = self.get_user_by_username(norm)
        if existing and existing.id != user.id:
            raise UsernameAlreadyExistsError("Deze gebruikersnaam is al in gebruik")

        now = _utcnow()
        if user.username_changed_at:
            elapsed_days = (now - user.username_changed_at).days
            if elapsed_days < settings.USERNAME_CHANGE_COOLDOWN_DAYS:
                remaining = settings.USERNAME_CHANGE_COOLDOWN_DAYS - elapsed_days
                raise UsernameCooldownError(
                    "Je kunt je gebruikersnaam maximaal één keer per 30 dagen "
                    f"wijzigen. Probeer het over {remaining} dag(en) opnieuw."
                )

        user.username = norm
        user.username_changed_at = now
        self.db.commit()
        self.db.refresh(user)
        return user

    def request_email_change(
        self, user: User, new_email: str, current_password: str
    ) -> tuple[bool, str, str | None]:
        """Request email change with password verification and unverified transition."""
        if not verify_password(current_password, user.password_hash):
            raise InvalidPasswordError("Huidig wachtwoord is onjuist")

        norm_new = new_email.strip().lower()
        if norm_new == user.email.lower():
            raise ValueError(
                "Het nieuwe e-mailadres is gelijk aan je huidige e-mailadres"
            )

        msg = (
            "Als het nieuwe e-mailadres beschikbaar is, hebben we een "
            "verificatielink verstuurd."
        )
        existing = self.get_user_by_email(norm_new)
        if existing and existing.id != user.id:
            # Non-enumerating response
            return (True, msg, None)

        _, raw_token = self.create_email_verification(
            user_id=user.id,
            token_type="email_change",
            target_email=norm_new,
        )
        logger.info(
            "Issued email change verification token for %s -> %s: %s",
            user.email,
            norm_new,
            raw_token,
        )
        return (True, msg, raw_token)

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

    def claim_anonymous_session(
        self,
        user: User,
        anonymous_session_id: str,
    ) -> int:
        """Transfer collection items, scans, and sessions from an anonymous
        pilot session to user.
        """
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
                existing_user_item.quantity += item.quantity
                existing_user_item.version += 1
                existing_user_item.updated_at = _utcnow()

                self.db.query(CollectionScanLink).filter(
                    CollectionScanLink.collection_item_id == item.id
                ).update({"collection_item_id": existing_user_item.id})

                self.db.delete(item)
            else:
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

        self.db.commit()
        return claimed_items_count
