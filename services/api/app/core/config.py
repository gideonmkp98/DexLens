import json
from typing import Any

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Pokémon TCG Scanner API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    # Database
    DATABASE_URL: str = (
        "mysql+pymysql://tcg_user:tcg_password@localhost:3306/tcg?charset=utf8mb4"
    )

    # CORS
    CORS_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # External APIs
    TCGDEX_BASE_URL: str = "https://api.tcgdex.net/v2"
    TCGDEX_HTTP_TIMEOUT: float = 10.0
    IMPORT_MAX_RETRIES: int = 3
    IMPORT_RETRY_BACKOFF: float = 1.0
    SUPPORTED_LANGUAGES: list[str] = ["en"]

    # Image upload limits and processing
    UPLOAD_MAX_BYTES: int = 15728640  # 15 MiB
    UPLOAD_MAX_PIXELS: int = 40000000  # 40 MP
    UPLOAD_MAX_DIMENSION: int = 2500  # pixels on longest edge
    UPLOAD_JPEG_QUALITY: int = 90  # 1-100
    UPLOAD_RETENTION_HOURS: int = 24  # temporary scan lifetime
    UPLOAD_DIRECTORY: str = "/tmp/tcg_uploads"  # filesystem storage root
    UPLOAD_REQUEST_OVERHEAD_BYTES: int = 262144  # 256 KiB multipart buffer

    # Detail in-memory caching
    DETAIL_CACHE_TTL_SECONDS: int = 21600  # 6 hours
    DETAIL_CACHE_MAX_ENTRIES: int = 500
    DETAIL_CACHE_MAX_STALE_SECONDS: int = 86400  # 24 hours
    DETAIL_CACHE_FAILED_COOLDOWN_SECONDS: int = 60  # 1 minute

    # OCR and Recognition Configuration
    OCR_ENGINE: str = "tesseract"
    OCR_TIMEOUT_SECONDS: float = 15.0
    OCR_MAX_CONCURRENCY: int = 3
    OCR_MAX_IMAGE_DIMENSION: int = 2000

    # Phase 8: Auth, Analytics, and Pilot Configuration
    SECURE_COOKIES: bool = False
    PILOT_ADMIN_SECRET: str = "pilot-secret-dev"
    ANALYTICS_RETENTION_DAYS: int = 30
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10
    ANALYTICS_RATE_LIMIT_PER_MINUTE: int = 60
    GENERAL_API_RATE_LIMIT_PER_MINUTE: int = 60
    ANALYTICS_MAX_PAYLOAD_BYTES: int = 2048
    TRUSTED_PROXY_IPS: list[str] | str = []

    # Phase 9: Account Security Configuration
    HIBP_API_ENABLED: bool = True
    HIBP_API_TIMEOUT_SECONDS: float = 2.0
    HIBP_FAIL_CLOSED: bool = False
    PASSWORD_MIN_LENGTH: int = 15
    PASSWORD_MAX_LENGTH: int = 128
    EMAIL_VERIFICATION_EXPIRE_HOURS: int = 24
    EMAIL_VERIFICATION_RESEND_COOLDOWN_SECONDS: int = 60
    USERNAME_CHANGE_COOLDOWN_DAYS: int = 30
    REGISTRATION_NON_ENUMERATION: bool = False

    # Phase 9: Beta Access & Invitation Configuration
    REGISTRATION_MODE: str = "open"  # "open", "beta_code_required", "invite_only"
    EMAIL_PROVIDER: str = "memory"  # "memory", "console"
    EMAIL_FROM: str = "DexLens <noreply@example.com>"
    EMAIL_PUBLIC_BASE_URL: str = "http://localhost:3000"
    EMAIL_DELIVERY_TIMEOUT_SECONDS: float = 10.0
    RESEND_API_KEY: str | None = None
    RESEND_API_URL: str = "https://api.resend.com/emails"
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True
    INVITATION_EXPIRE_DAYS: int = 7
    DEFAULT_BETA_SCAN_QUOTA: int = 50

    # Daily Scan Quota Configuration
    DEFAULT_DAILY_SCAN_LIMIT: int = 50

    # Phase 9: Admin, Quota, and Cloudflare Turnstile / Abuse Prevention Configuration
    TURNSTILE_SECRET_KEY: str | None = None
    TURNSTILE_SITE_KEY: str | None = None
    TURNSTILE_ENABLED: bool = False
    TURNSTILE_TEST_MODE: bool = False
    TURNSTILE_VERIFY_URL: str = (
        "https://challenges.cloudflare.com/turnstile/v0/siteverify"
    )
    TURNSTILE_EXPECTED_HOSTNAME: str | None = None
    TURNSTILE_TOKEN_TTL_SECONDS: int = 300
    SCAN_BURST_WINDOW_SECONDS: int = 15
    SCAN_BURST_THRESHOLD: int = 5
    SCAN_HARD_RATE_LIMIT_PER_MINUTE: int = 30
    GLOBAL_DEFAULT_DAILY_SCAN_QUOTA: int = 100
    GLOBAL_DEFAULT_HOURLY_SCAN_QUOTA: int = 30

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if self.ENVIRONMENT.lower() in {"production", "prod"}:
            if not self.SECURE_COOKIES:
                raise ValueError("SECURE_COOKIES must be true in production")
            if (
                self.PILOT_ADMIN_SECRET == "pilot-secret-dev"
                or self.PILOT_ADMIN_SECRET.startswith("replace-")
                or len(self.PILOT_ADMIN_SECRET) < 32
            ):
                raise ValueError(
                    "PILOT_ADMIN_SECRET must be a non-default 32+ character secret "
                    "in production"
                )
            provider_norm = self.EMAIL_PROVIDER.lower().strip()
            if provider_norm in {"memory", "console"}:
                raise ValueError(
                    "In-memory and console email providers are not permitted in "
                    "production. A production email provider must be configured."
                )
            valid_providers = {"resend", "smtp"}
            if provider_norm not in valid_providers:
                raise ValueError(
                    f"Invalid EMAIL_PROVIDER '{self.EMAIL_PROVIDER}' for production. "
                    f"Must be one of: {', '.join(sorted(valid_providers))}."
                )
            if provider_norm == "resend" and not self.RESEND_API_KEY:
                raise ValueError(
                    "RESEND_API_KEY must be configured when EMAIL_PROVIDER=resend"
                )
            if provider_norm == "smtp" and not self.SMTP_HOST:
                raise ValueError(
                    "SMTP_HOST must be configured when EMAIL_PROVIDER=smtp"
                )
            if self.TURNSTILE_TEST_MODE:
                raise ValueError("TURNSTILE_TEST_MODE cannot be enabled in production")
            if self.TURNSTILE_ENABLED:
                if (
                    not self.TURNSTILE_SECRET_KEY
                    or self.TURNSTILE_SECRET_KEY.startswith("replace-")
                ):
                    raise ValueError(
                        "TURNSTILE_SECRET_KEY must be configured with a valid "
                        "Cloudflare secret in production"
                    )
                if (
                    self.TURNSTILE_SECRET_KEY.startswith("1x00")
                    or self.TURNSTILE_SECRET_KEY.startswith("2x00")
                    or self.TURNSTILE_SECRET_KEY.startswith("3x00")
                ):
                    raise ValueError(
                        "Cloudflare test secret keys are forbidden in production"
                    )
                if not self.TURNSTILE_SITE_KEY or self.TURNSTILE_SITE_KEY.startswith(
                    "replace-"
                ):
                    raise ValueError(
                        "TURNSTILE_SITE_KEY must be configured with a valid "
                        "Cloudflare site key in production"
                    )
                if (
                    self.TURNSTILE_SITE_KEY.startswith("1x00")
                    or self.TURNSTILE_SITE_KEY.startswith("2x00")
                    or self.TURNSTILE_SITE_KEY.startswith("3x00")
                ):
                    raise ValueError(
                        "Cloudflare test site keys are forbidden in production"
                    )
        if self.REGISTRATION_MODE not in {"open", "beta_code_required", "invite_only"}:
            raise ValueError(
                f"Invalid REGISTRATION_MODE: {self.REGISTRATION_MODE}. "
                "Must be one of: open, beta_code_required, invite_only."
            )
        return self

    @field_validator(
        "UPLOAD_MAX_BYTES",
        "UPLOAD_MAX_PIXELS",
        "UPLOAD_MAX_DIMENSION",
        "UPLOAD_RETENTION_HOURS",
        mode="after",
    )
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("Value must be strictly positive")
        return v

    @field_validator("UPLOAD_JPEG_QUALITY", mode="after")
    @classmethod
    def validate_quality(cls, v: int) -> int:
        if not (1 <= v <= 100):
            raise ValueError("JPEG quality must be between 1 and 100")
        return v

    @field_validator("UPLOAD_REQUEST_OVERHEAD_BYTES", mode="after")
    @classmethod
    def validate_overhead_bytes(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Overhead bytes must be non-negative")
        return v

    @field_validator("DEFAULT_DAILY_SCAN_LIMIT", mode="after")
    @classmethod
    def validate_default_daily_scan_limit(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Default daily scan limit must be non-negative")
        return v

    @field_validator("CORS_ORIGINS", "TRUSTED_PROXY_IPS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            stripped = v.strip()
            if not stripped:
                return []
            if stripped.startswith("["):
                parsed = json.loads(stripped)
                return [str(origin).strip() for origin in parsed]
            return [origin.strip() for origin in stripped.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(origin).strip() for origin in v]
        return []


settings = Settings()
