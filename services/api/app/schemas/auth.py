import re
from datetime import datetime
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.config import settings

USERNAME_REGEX = re.compile(r"^[a-z0-9_-]{3,30}$")
EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_username(v: str | None) -> str | None:
    if v is None:
        return None
    clean = v.strip().lower()
    if not USERNAME_REGEX.match(clean):
        raise ValueError(
            "Gebruikersnaam moet tussen 3 en 30 tekens lang zijn en mag "
            "alleen letters, cijfers, streepjes en underscores bevatten"
        )
    return clean


def normalize_email(v: str) -> str:
    clean = v.strip().lower()
    if not EMAIL_REGEX.match(clean):
        raise ValueError("Ongeldig e-mailadres")
    if len(clean) > 255:
        raise ValueError("E-mailadres is te lang (maximaal 255 tekens)")
    return clean


def validate_password_policy(v: str) -> str:
    """Enforce modern NIST SP 800-63B password policy:

    - Minimum 15 characters for password-only authentication
    - Support at least 64 characters (up to 128 characters)
    - Allow Unicode, spaces, paste, and password managers
    - No arbitrary composition rules (no mandatory upper/lower/digits/symbols)
    - No forced periodic changes
    """
    if len(v) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Wachtwoord moet minimaal {settings.PASSWORD_MIN_LENGTH} tekens lang zijn"
        )
    if len(v) > settings.PASSWORD_MAX_LENGTH:
        raise ValueError(
            f"Wachtwoord is te lang (maximaal {settings.PASSWORD_MAX_LENGTH} tekens)"
        )
    return v


class RegisterRequest(BaseModel):
    username: str | None = None
    email: str
    password: str
    password_confirmation: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "password_confirmation", "password_confirm", "confirm_password"
        ),
    )
    accepted_policies: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "accepted_policies", "accept_policies", "accept_terms"
        ),
    )
    beta_code: str | None = None
    invite_token: str | None = None

    @field_validator("username")
    @classmethod
    def validate_username_field(cls, v: str | None) -> str | None:
        return normalize_username(v)

    @field_validator("email")
    @classmethod
    def validate_email_field(cls, v: str) -> str:
        return normalize_email(v)

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, v: str) -> str:
        return validate_password_policy(v)

    @model_validator(mode="after")
    def validate_confirmation_and_policies(self) -> "RegisterRequest":
        if self.password_confirmation is not None:
            if self.password_confirmation != self.password:
                raise ValueError("Wachtwoorden komen niet overeen")
        if not self.accepted_policies:
            raise ValueError(
                "Je moet akkoord gaan met de gebruiksvoorwaarden en het privacybeleid"
            )
        return self

    @field_validator("beta_code", "invite_token")
    @classmethod
    def clean_optional_token(cls, v: str | None) -> str | None:
        if v is None:
            return None
        clean = v.strip()
        return clean if clean else None


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class ChangeUsernameRequest(BaseModel):
    username: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        res = normalize_username(v)
        if not res:
            raise ValueError("Gebruikersnaam is verplicht")
        return res


class RequestEmailChangeRequest(BaseModel):
    new_email: str
    current_password: str

    @field_validator("new_email")
    @classmethod
    def validate_new_email(cls, v: str) -> str:
        return normalize_email(v)


class VerifyEmailRequest(BaseModel):
    token: str


class ResendVerificationRequest(BaseModel):
    email: str | None = None

    @field_validator("email")
    @classmethod
    def validate_optional_email(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        return normalize_email(v)


class ClaimAnonymousSessionRequest(BaseModel):
    anonymous_session_id: str
    anonymous_session_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    username: str | None = None
    role: str
    is_active: bool
    email_verified: bool = False
    policies_accepted_at: datetime | None = None
    username_changed_at: datetime | None = None
    has_beta_access: bool = False
    beta_entitlement: str | None = None
    scan_quota: int | None = None
    created_at: datetime

    @field_validator("scan_quota", mode="before")
    @classmethod
    def extract_scan_quota(cls, v: Any) -> int | None:
        if v is None:
            return None
        if isinstance(v, int):
            return v
        if hasattr(v, "custom_limit"):
            return v.custom_limit
        return None


class MeResponse(BaseModel):
    is_authenticated: bool
    user: UserResponse | None = None
    session_id: str
    session_type: str


class AccountMessageResponse(BaseModel):
    message: str
    email_verified: bool | None = None


class ClaimAnonymousSessionResponse(BaseModel):
    claimed_items_count: int
    message: str
