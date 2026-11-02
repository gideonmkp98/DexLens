import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class RegisterRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(r"^[^@]+@[^@]+\.[^@]+$", clean):
            raise ValueError("Ongeldig e-mailadres")
        if len(clean) > 255:
            raise ValueError("E-mailadres is te lang")
        return clean

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Wachtwoord moet minimaal 8 tekens lang zijn")
        if len(v) > 128:
            raise ValueError("Wachtwoord is te lang (maximaal 128 tekens)")
        return v


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def clean_email(cls, v: str) -> str:
        return v.strip().lower()


class ClaimAnonymousSessionRequest(BaseModel):
    anonymous_session_id: str
    anonymous_session_token: str


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    role: str
    is_active: bool
    created_at: datetime


class MeResponse(BaseModel):
    is_authenticated: bool
    user: UserResponse | None = None
    session_id: str
    session_type: str


class ClaimAnonymousSessionResponse(BaseModel):
    claimed_items_count: int
    message: str
