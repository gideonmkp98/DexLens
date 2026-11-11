import hashlib
import logging
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.email import BaseEmailProvider, get_email_provider
from app.models.app_setting import AppSetting
from app.models.beta_access import BetaCode, BetaCodeRedemption, Invitation
from app.models.user import User
from app.schemas.beta_access import RegistrationMode
from app.services.auth import hash_ip

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def mask_email(email: str) -> str:
    """Mask email for safe client exposure: j***@example.com."""
    parts = email.split("@")
    if len(parts) != 2:
        return "***"
    name, domain = parts
    if len(name) <= 2:
        masked_name = name[0] + "***"
    else:
        masked_name = name[0] + "***" + name[-1]
    return f"{masked_name}@{domain}"


# Structured Error Classes with Stable Error Codes


class BetaAccessError(Exception):
    """Base exception for beta access and invitation operations."""

    def __init__(self, message: str, code: str = "BETA_ACCESS_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class RegistrationModeBlockedError(BetaAccessError):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message, code=code)


class BetaCodeInvalidError(BetaAccessError):
    def __init__(self, message: str = "Bètacode is ongeldig") -> None:
        super().__init__(message, code="INVALID_BETA_CODE")


class BetaCodeExpiredError(BetaAccessError):
    def __init__(self, message: str = "Bètacode is verlopen") -> None:
        super().__init__(message, code="EXPIRED_BETA_CODE")


class BetaCodeRevokedError(BetaAccessError):
    def __init__(self, message: str = "Bètacode is ingetrokken") -> None:
        super().__init__(message, code="REVOKED_BETA_CODE")


class BetaCodeExhaustedError(BetaAccessError):
    def __init__(
        self,
        message: str = "Bètacode heeft het maximale aantal registraties bereikt",
    ) -> None:
        super().__init__(message, code="EXHAUSTED_BETA_CODE")


class BetaCodeEmailMismatchError(BetaAccessError):
    def __init__(
        self, message: str = "Bètacode is niet geldig voor dit e-mailadres"
    ) -> None:
        super().__init__(message, code="BETA_CODE_EMAIL_MISMATCH")


class BetaCodeAlreadyRedeemedError(BetaAccessError):
    def __init__(
        self, message: str = "Bètacode is al verzilverd voor dit account"
    ) -> None:
        super().__init__(message, code="BETA_CODE_ALREADY_REDEEMED")


class InvitationInvalidError(BetaAccessError):
    def __init__(self, message: str = "Uitnodigingstoken is ongeldig") -> None:
        super().__init__(message, code="INVALID_INVITATION")


class InvitationUsedError(BetaAccessError):
    def __init__(self, message: str = "Deze uitnodiging is al gebruikt") -> None:
        super().__init__(message, code="INVITATION_ALREADY_USED")


class InvitationExpiredError(BetaAccessError):
    def __init__(self, message: str = "Deze uitnodiging is verlopen") -> None:
        super().__init__(message, code="EXPIRED_INVITATION")


class InvitationRevokedError(BetaAccessError):
    def __init__(self, message: str = "Deze uitnodiging is ingetrokken") -> None:
        super().__init__(message, code="REVOKED_INVITATION")


class InvitationEmailMismatchError(BetaAccessError):
    def __init__(
        self,
        message: str = "Dit uitnodigingstoken is niet geldig voor dit e-mailadres",
    ) -> None:
        super().__init__(message, code="INVITATION_EMAIL_MISMATCH")


class ConcurrentClaimLostError(BetaAccessError):
    def __init__(
        self, message: str = "De bètacode is zojuist door een andere gebruiker geclaimd"
    ) -> None:
        super().__init__(message, code="CONCURRENT_CLAIM_LOST")


class BetaAccessService:
    """Service managing beta codes, email invitations, and registration modes."""

    def __init__(
        self,
        db: Session,
        email_provider: BaseEmailProvider | None = None,
    ) -> None:
        self.db = db
        self.email_provider = email_provider or get_email_provider()

    # --- Registration Mode Management ---

    @classmethod
    def get_mode(cls, db: Session | None = None) -> RegistrationMode:
        return cls._fetch_registration_mode(db)

    @classmethod
    def set_mode(cls, mode: RegistrationMode, db: Session) -> None:
        cls._persist_registration_mode(mode, db)

    @classmethod
    def reset_mode(cls, db: Session | None = None) -> None:
        if db is not None:
            try:
                db.query(AppSetting).filter(
                    AppSetting.key == "registration_mode"
                ).delete()
                db.commit()
            except Exception as exc:
                db.rollback()
                logger.warning("Could not reset registration_mode: %s", exc)

    def get_registration_mode(self, db: Session | None = None) -> RegistrationMode:
        target_db = db or getattr(self, "db", None)
        return self._fetch_registration_mode(target_db)

    def set_registration_mode(
        self, mode: RegistrationMode, db: Session | None = None
    ) -> None:
        target_db = db or getattr(self, "db", None)
        if target_db is None:
            raise ValueError(
                "A database session is required to persist registration mode"
            )
        self._persist_registration_mode(mode, target_db)

    @classmethod
    def reset_registration_mode(cls, db: Session | None = None) -> None:
        cls.reset_mode(db)

    @staticmethod
    def _fetch_registration_mode(db: Session | None) -> RegistrationMode:
        """Fetch registration mode from database, fallback to env setting."""
        if db is not None:
            try:
                setting = (
                    db.query(AppSetting)
                    .filter(AppSetting.key == "registration_mode")
                    .first()
                )
                if setting and setting.value:
                    return RegistrationMode(setting.value.strip().lower())
            except Exception as exc:
                logger.warning(
                    "Could not read registration_mode from database, falling back: %s",
                    exc,
                )

        try:
            return RegistrationMode(settings.REGISTRATION_MODE.strip().lower())
        except ValueError:
            return RegistrationMode.OPEN

    @staticmethod
    def _persist_registration_mode(mode: RegistrationMode, db: Session) -> None:
        """Persist registration mode into app_settings table."""
        now = _utcnow()
        setting = (
            db.query(AppSetting)
            .filter(AppSetting.key == "registration_mode")
            .with_for_update()
            .first()
        )
        if setting:
            setting.value = mode.value
            setting.updated_at = now
        else:
            setting = AppSetting(
                key="registration_mode", value=mode.value, updated_at=now
            )
            db.add(setting)
        db.commit()
        logger.info("Persisted server registration mode updated to: %s", mode.value)

    # --- Beta Code Cryptography & Normalization ---

    @staticmethod
    def normalize_code(code: str) -> str:
        return code.strip().upper()

    @staticmethod
    def hash_code(code: str) -> str:
        normalized = BetaAccessService.normalize_code(code)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_random_code() -> str:
        """Generate high-entropy human-friendly beta code: BETA-XXXX-XXXX."""
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        return f"BETA-{part1}-{part2}"

    # --- Beta Code CRUD & Lifecycle ---

    def create_beta_code(
        self,
        label: str,
        max_uses: int | None = None,
        expires_at: datetime | None = None,
        allowed_email: str | None = None,
        scan_quota_allocated: int | None = None,
        beta_entitlement: str | None = None,
        custom_code: str | None = None,
        created_by_user_id: str | None = None,
    ) -> tuple[BetaCode, str]:
        """Create a new beta code. Plaintext code is returned once to creator."""
        if custom_code:
            plain_code = self.normalize_code(custom_code)
        else:
            plain_code = self.generate_random_code()

        code_hash = self.hash_code(plain_code)
        existing = (
            self.db.query(BetaCode).filter(BetaCode.code_hash == code_hash).first()
        )
        if existing:
            raise BetaAccessError(
                "Een code met deze hash bestaat al", code="CODE_EXISTS"
            )

        norm_allowed_email = allowed_email.strip().lower() if allowed_email else None
        code_prefix = plain_code[:8] if len(plain_code) >= 8 else plain_code

        beta_code = BetaCode(
            id=str(uuid.uuid4()),
            code_hash=code_hash,
            code_prefix=code_prefix,
            label=label.strip(),
            is_active=True,
            max_uses=max_uses,
            used_count=0,
            allowed_email=norm_allowed_email,
            scan_quota_allocated=scan_quota_allocated,
            beta_entitlement=beta_entitlement,
            expires_at=expires_at,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(beta_code)
        self.db.commit()
        self.db.refresh(beta_code)
        return beta_code, plain_code

    def get_beta_code_by_id(self, code_id: str) -> BetaCode | None:
        return self.db.query(BetaCode).filter(BetaCode.id == code_id).first()

    def get_beta_code_by_raw_code(self, raw_code: str) -> BetaCode | None:
        code_hash = self.hash_code(raw_code)
        return self.db.query(BetaCode).filter(BetaCode.code_hash == code_hash).first()

    def list_beta_codes(
        self,
        skip: int = 0,
        limit: int = 50,
        active_only: bool = False,
    ) -> tuple[list[BetaCode], int]:
        query = self.db.query(BetaCode)
        if active_only:
            query = query.filter(BetaCode.is_active.is_(True))
        total = query.count()
        items = (
            query.order_by(BetaCode.created_at.desc()).offset(skip).limit(limit).all()
        )
        return items, total

    def revoke_beta_code(
        self,
        code_id: str,
        revoked_by_user_id: str | None = None,
    ) -> BetaCode:
        code = self.get_beta_code_by_id(code_id)
        if not code:
            raise BetaCodeInvalidError("Bètacode niet gevonden")
        if not code.is_active:
            return code

        now = _utcnow()
        code.is_active = False
        code.revoked_at = now
        code.revoked_by_user_id = revoked_by_user_id
        code.updated_at = now
        self.db.commit()
        self.db.refresh(code)
        return code

    def validate_beta_code(
        self,
        code_str: str,
        email: str | None = None,
    ) -> tuple[bool, str, BetaCode | None]:
        """Validate if a beta code can be redeemed. Never leaks secrets in messages."""
        if not code_str:
            return False, "Bètacode is vereist", None

        code = self.get_beta_code_by_raw_code(code_str)
        if not code:
            return False, "Bètacode is ongeldig", None

        now = _utcnow()
        if not code.is_active:
            return False, "Bètacode is ingetrokken of inactief", None

        if code.expires_at and code.expires_at <= now:
            return False, "Bètacode is verlopen", None

        if code.max_uses is not None and code.used_count >= code.max_uses:
            return (
                False,
                "Bètacode heeft het maximale aantal registraties bereikt",
                None,
            )

        if code.allowed_email and email:
            norm_email = email.strip().lower()
            if code.allowed_email != norm_email:
                return False, "Bètacode is niet geldig voor dit e-mailadres", None

        return True, "Bètacode is geldig", code

    def redeem_beta_code(
        self,
        code_str: str,
        user: User,
        ip: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[BetaCode, BetaCodeRedemption]:
        """Atomically redeem a beta code for an authenticated user account."""
        valid, msg, code = self.validate_beta_code(code_str, user.email)
        if not valid or not code:
            raise BetaCodeInvalidError(msg)

        # Check existing redemption for this user
        existing_redemption = (
            self.db.query(BetaCodeRedemption)
            .filter(
                BetaCodeRedemption.beta_code_id == code.id,
                BetaCodeRedemption.user_id == user.id,
            )
            .first()
        )
        if existing_redemption:
            raise BetaCodeAlreadyRedeemedError()

        now = _utcnow()

        # Atomic increment with conditional guard against over-redemption
        stmt = (
            update(BetaCode)
            .where(
                BetaCode.id == code.id,
                BetaCode.is_active.is_(True),
                or_(BetaCode.expires_at.is_(None), BetaCode.expires_at > now),
                or_(
                    BetaCode.max_uses.is_(None),
                    BetaCode.used_count < BetaCode.max_uses,
                ),
            )
            .values(
                used_count=BetaCode.used_count + 1,
                updated_at=now,
            )
        )
        result = self.db.execute(stmt)
        if result.rowcount == 0:
            self.db.rollback()
            raise BetaCodeExhaustedError()

        # Record redemption audit row
        redemption = BetaCodeRedemption(
            id=str(uuid.uuid4()),
            beta_code_id=code.id,
            user_id=user.id,
            redeemed_at=now,
            ip_hash=hash_ip(ip),
            user_agent=user_agent[:255] if user_agent else None,
        )
        self.db.add(redemption)

        # Apply entitlements and quota to user
        user.has_beta_access = True
        if code.beta_entitlement:
            user.beta_entitlement = code.beta_entitlement
        elif not user.beta_entitlement:
            user.beta_entitlement = "beta"

        if code.scan_quota_allocated is not None:
            from app.services.scan_quota import ScanQuotaService

            quota_service = ScanQuotaService(self.db)
            override = quota_service.get_user_override(user.id)
            current_limit = (
                override.custom_limit
                if (override and override.custom_limit is not None)
                else quota_service.get_global_default_limit()
            )
            new_limit = current_limit + code.scan_quota_allocated
            quota_service.set_user_override(
                user_id=user.id,
                override_mode="custom",
                custom_limit=new_limit,
                reason=f"Beta code allocation ({code.code_prefix})",
            )

        self.db.commit()
        self.db.refresh(code)
        self.db.refresh(redemption)
        return code, redemption

    # --- Invitation Cryptography & Normalization ---

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def generate_invite_token() -> str:
        """Generate cryptographically secure 256-bit URL-safe token."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def hash_invite_token(token: str) -> str:
        return hashlib.sha256(token.strip().encode("utf-8")).hexdigest()

    # --- Personal Invitation CRUD & Lifecycle ---

    def create_invitation(
        self,
        email: str,
        expires_in_days: int | None = None,
        scan_quota_allocated: int | None = None,
        beta_entitlement: str | None = None,
        created_by_user_id: str | None = None,
    ) -> tuple[Invitation, str]:
        """Create and dispatch personal email invitation with hashed token."""
        norm_email = self.normalize_email(email)
        plain_token = self.generate_invite_token()
        token_hash = self.hash_invite_token(plain_token)

        duration = expires_in_days or settings.INVITATION_EXPIRE_DAYS
        now = _utcnow()
        expires_at = now + timedelta(days=duration)

        invitation = Invitation(
            id=str(uuid.uuid4()),
            email=norm_email,
            token_hash=token_hash,
            status="pending",
            expires_at=expires_at,
            sent_at=now,
            resend_count=0,
            scan_quota_allocated=scan_quota_allocated,
            beta_entitlement=beta_entitlement,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)

        # Dispatch email
        try:
            self.email_provider.send_invitation(
                to_email=norm_email,
                invite_token=plain_token,
                expires_at=expires_at,
                invitation_id=invitation.id,
                beta_entitlement=beta_entitlement,
            )
        except Exception as exc:
            logger.error("Failed to send invitation email: %s", exc)

        return invitation, plain_token

    def get_invitation_by_id(self, invite_id: str) -> Invitation | None:
        return self.db.query(Invitation).filter(Invitation.id == invite_id).first()

    def get_invitation_by_raw_token(self, raw_token: str) -> Invitation | None:
        token_hash = self.hash_invite_token(raw_token)
        return (
            self.db.query(Invitation)
            .filter(Invitation.token_hash == token_hash)
            .first()
        )

    def list_invitations(
        self,
        skip: int = 0,
        limit: int = 50,
        status_filter: str | None = None,
    ) -> tuple[list[Invitation], int]:
        query = self.db.query(Invitation)
        if status_filter:
            query = query.filter(Invitation.status == status_filter)
        total = query.count()
        items = (
            query.order_by(Invitation.created_at.desc()).offset(skip).limit(limit).all()
        )
        return items, total

    def validate_invitation(
        self,
        token_str: str,
    ) -> tuple[bool, str, Invitation | None]:
        """Validate if an invitation token is active and unexpired."""
        if not token_str:
            return False, "Uitnodigingstoken is vereist", None

        invitation = self.get_invitation_by_raw_token(token_str)
        if not invitation:
            return False, "Uitnodigingstoken is ongeldig", None

        now = _utcnow()
        if invitation.status == "accepted":
            return False, "Deze uitnodiging is al gebruikt", None

        if invitation.status == "revoked":
            return False, "Deze uitnodiging is ingetrokken", None

        if invitation.expires_at <= now:
            if invitation.status != "expired":
                invitation.status = "expired"
                try:
                    self.db.commit()
                except Exception:
                    self.db.rollback()
            return False, "Deze uitnodiging is verlopen", None

        if invitation.status != "pending":
            return False, "Uitnodiging is niet meer geldig", None

        return True, "Uitnodiging is geldig", invitation

    def redeem_invitation(
        self,
        token_str: str,
        user: User,
    ) -> Invitation:
        """Atomically complete and bind invitation to the registering user."""
        valid, msg, invitation = self.validate_invitation(token_str)
        if not valid or not invitation:
            raise InvitationInvalidError(msg)

        norm_user_email = self.normalize_email(user.email)
        norm_invite_email = self.normalize_email(invitation.email)

        if norm_user_email != norm_invite_email:
            raise InvitationEmailMismatchError()

        now = _utcnow()

        # Atomic update prevents replay and concurrent redemption
        stmt = (
            update(Invitation)
            .where(
                Invitation.id == invitation.id,
                Invitation.status == "pending",
                Invitation.expires_at > now,
            )
            .values(
                status="accepted",
                accepted_at=now,
                accepted_by_user_id=user.id,
                updated_at=now,
            )
        )
        result = self.db.execute(stmt)
        if result.rowcount == 0:
            self.db.rollback()
            raise InvitationUsedError()

        # Apply entitlements and quota
        user.has_beta_access = True
        if invitation.beta_entitlement:
            user.beta_entitlement = invitation.beta_entitlement
        elif not user.beta_entitlement:
            user.beta_entitlement = "beta"

        if invitation.scan_quota_allocated is not None:
            from app.services.scan_quota import ScanQuotaService

            quota_service = ScanQuotaService(self.db)
            override = quota_service.get_user_override(user.id)
            current_limit = (
                override.custom_limit
                if (override and override.custom_limit is not None)
                else quota_service.get_global_default_limit()
            )
            new_limit = current_limit + invitation.scan_quota_allocated
            quota_service.set_user_override(
                user_id=user.id,
                override_mode="custom",
                custom_limit=new_limit,
                reason=f"Invitation allocation ({invitation.email})",
            )

        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def revoke_invitation(
        self,
        invite_id: str,
        revoked_by_user_id: str | None = None,
    ) -> Invitation:
        invitation = self.get_invitation_by_id(invite_id)
        if not invitation:
            raise InvitationInvalidError("Uitnodiging niet gevonden")

        if invitation.status == "accepted":
            raise BetaAccessError(
                "Kan een geaccepteerde uitnodiging niet intrekken",
                code="INVITATION_ALREADY_ACCEPTED",
            )

        now = _utcnow()
        invitation.status = "revoked"
        invitation.revoked_at = now
        invitation.revoked_by_user_id = revoked_by_user_id
        invitation.updated_at = now
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def resend_invitation(
        self,
        invite_id: str,
        expires_in_days: int | None = None,
    ) -> tuple[Invitation, str]:
        """Resend invitation with a newly generated token, invalidating prior token."""
        invitation = self.get_invitation_by_id(invite_id)
        if not invitation:
            raise InvitationInvalidError("Uitnodiging niet gevonden")

        if invitation.status == "accepted":
            raise BetaAccessError(
                "Kan een geaccepteerde uitnodiging niet opnieuw versturen",
                code="INVITATION_ALREADY_ACCEPTED",
            )

        new_token = self.generate_invite_token()
        new_token_hash = self.hash_invite_token(new_token)

        duration = expires_in_days or settings.INVITATION_EXPIRE_DAYS
        now = _utcnow()
        new_expires_at = now + timedelta(days=duration)

        invitation.token_hash = new_token_hash
        invitation.status = "pending"
        invitation.expires_at = new_expires_at
        invitation.sent_at = now
        invitation.resend_count += 1
        invitation.updated_at = now

        self.db.commit()
        self.db.refresh(invitation)

        # Dispatch email
        try:
            self.email_provider.send_invitation(
                to_email=invitation.email,
                invite_token=new_token,
                expires_at=new_expires_at,
                invitation_id=invitation.id,
                beta_entitlement=invitation.beta_entitlement,
            )
        except Exception as exc:
            logger.error("Failed to resend invitation email: %s", exc)

        return invitation, new_token

    # --- Unit of Work: Lock and Consume Credential ---

    def lock_and_consume_credential(
        self,
        email: str,
        beta_code_str: str | None = None,
        invite_token_str: str | None = None,
    ) -> tuple[BetaCode | None, Invitation | None, str | None, int | None]:
        """Enforces registration mode, locks credential with SELECT FOR UPDATE,
        validates all rules, and consumes usage UNCOMMITTED.

        Must be called within an active transaction. Does not commit.
        """
        mode = self.get_registration_mode(self.db)
        norm_email = self.normalize_email(email)

        # 1. Enforce mode requirements
        if mode == RegistrationMode.INVITE_ONLY:
            if not invite_token_str:
                raise RegistrationModeBlockedError(
                    "Registratie is alleen mogelijk op persoonlijke uitnodiging.",
                    code="REGISTRATION_INVITE_ONLY",
                )
        elif mode == RegistrationMode.BETA_CODE_REQUIRED:
            if not invite_token_str and not beta_code_str:
                raise RegistrationModeBlockedError(
                    "Een geldige bètacode is vereist om te registreren.",
                    code="REGISTRATION_BETA_CODE_REQUIRED",
                )

        now = _utcnow()

        # 2. Process invitation token if provided
        if invite_token_str:
            token_hash = self.hash_invite_token(invite_token_str)
            invitation = (
                self.db.query(Invitation)
                .filter(Invitation.token_hash == token_hash)
                .with_for_update()
                .first()
            )
            if not invitation:
                raise InvitationInvalidError("Uitnodigingstoken is ongeldig")

            if invitation.status == "accepted":
                raise InvitationUsedError()
            if invitation.status == "revoked":
                raise InvitationRevokedError()
            if invitation.expires_at <= now:
                invitation.status = "expired"
                raise InvitationExpiredError()
            if invitation.status != "pending":
                raise InvitationInvalidError("Uitnodiging is niet meer geldig")

            if self.normalize_email(invitation.email) != norm_email:
                raise InvitationEmailMismatchError()

            # Atomically claim uncommitted
            invitation.status = "accepted"
            invitation.accepted_at = now
            invitation.updated_at = now

            entitlement = invitation.beta_entitlement or "beta"
            quota = invitation.scan_quota_allocated
            return None, invitation, entitlement, quota

        # 3. Process beta code if provided
        if beta_code_str:
            code_hash = self.hash_code(beta_code_str)
            code = (
                self.db.query(BetaCode)
                .filter(BetaCode.code_hash == code_hash)
                .with_for_update()
                .first()
            )
            if not code:
                raise BetaCodeInvalidError("Bètacode is ongeldig")

            if not code.is_active:
                raise BetaCodeRevokedError("Bètacode is ingetrokken of inactief")

            if code.expires_at and code.expires_at <= now:
                raise BetaCodeExpiredError("Bètacode is verlopen")

            if code.max_uses is not None and code.used_count >= code.max_uses:
                raise BetaCodeExhaustedError()

            if code.allowed_email and code.allowed_email != norm_email:
                raise BetaCodeEmailMismatchError()

            # Atomically increment uncommitted
            code.used_count += 1
            code.updated_at = now

            entitlement = code.beta_entitlement or "beta"
            quota = code.scan_quota_allocated
            return code, None, entitlement, quota

        # 4. Mode is OPEN with no credentials
        return None, None, None, None

    # Backward-compatibility alias
    def verify_registration_requirements(
        self,
        email: str,
        beta_code: str | None = None,
        invite_token: str | None = None,
    ) -> tuple[BetaCode | None, Invitation | None]:
        """Validate registration eligibility without locking."""
        mode = self.get_registration_mode(self.db)
        norm_email = self.normalize_email(email)

        if mode == RegistrationMode.INVITE_ONLY:
            if not invite_token:
                raise RegistrationModeBlockedError(
                    "Registratie is alleen mogelijk op persoonlijke uitnodiging.",
                    code="REGISTRATION_INVITE_ONLY",
                )
            valid, msg, invitation = self.validate_invitation(invite_token)
            if not valid or not invitation:
                raise InvitationInvalidError(msg)
            if self.normalize_email(invitation.email) != norm_email:
                raise InvitationEmailMismatchError()
            return None, invitation

        if mode == RegistrationMode.BETA_CODE_REQUIRED:
            if invite_token:
                valid, msg, invitation = self.validate_invitation(invite_token)
                if not valid or not invitation:
                    raise InvitationInvalidError(msg)
                if self.normalize_email(invitation.email) != norm_email:
                    raise InvitationEmailMismatchError()
                return None, invitation

            if not beta_code:
                raise RegistrationModeBlockedError(
                    "Een geldige bètacode is vereist om te registreren.",
                    code="REGISTRATION_BETA_CODE_REQUIRED",
                )
            valid, msg, code = self.validate_beta_code(beta_code, norm_email)
            if not valid or not code:
                raise BetaCodeInvalidError(msg)
            return code, None

        matched_code: BetaCode | None = None
        matched_invitation: Invitation | None = None

        if invite_token:
            valid, msg, matched_invitation = self.validate_invitation(invite_token)
            if not valid or not matched_invitation:
                raise InvitationInvalidError(msg)
            if self.normalize_email(matched_invitation.email) != norm_email:
                raise InvitationEmailMismatchError()

        elif beta_code:
            valid, msg, matched_code = self.validate_beta_code(beta_code, norm_email)
            if not valid or not matched_code:
                raise BetaCodeInvalidError(msg)

        return matched_code, matched_invitation
