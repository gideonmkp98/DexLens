import json
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Pokémon TCG Scanner API"
    ENVIRONMENT: str = "development"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "mysql+pymysql://tcg_user:tcg_password@db:3306/tcg"

    CORS_ORIGINS: list[str] | str = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # TCGdex Catalog Provider Configuration
    TCGDEX_BASE_URL: str = "https://api.tcgdex.net/v2"
    TCGDEX_HTTP_TIMEOUT: float = 10.0
    IMPORT_MAX_RETRIES: int = 3
    IMPORT_RETRY_BACKOFF: float = 1.0
    SUPPORTED_LANGUAGES: list[str] = ["en"]

    # In-memory detail cache settings
    DETAIL_CACHE_TTL_SECONDS: int = 21600  # 6 hours
    DETAIL_CACHE_MAX_ENTRIES: int = 500
    DETAIL_CACHE_MAX_STALE_SECONDS: int = 86400  # 24 hours
    DETAIL_CACHE_FAILED_COOLDOWN_SECONDS: int = 60  # 1 minute

    # Upload and Scan Configuration
    UPLOAD_MAX_BYTES: int = 15728640  # 15 MiB default
    UPLOAD_MAX_PIXELS: int = 40000000  # 40M pixels
    UPLOAD_MAX_DIMENSION: int = 2500  # max normalized long edge
    UPLOAD_JPEG_QUALITY: int = 90  # JPEG quality (1-100)
    UPLOAD_RETENTION_HOURS: int = 24  # Scan retention period
    UPLOAD_DIRECTORY: str = "/app/uploads/scans"  # Storage path
    UPLOAD_REQUEST_OVERHEAD_BYTES: int = 262144  # 256 KiB multipart request overhead

    # Phase 5: OCR and Recognition Configuration
    OCR_ENGINE: str = "tesseract"
    OCR_TIMEOUT_SECONDS: float = 15.0
    OCR_MAX_CONCURRENCY: int = 3
    OCR_MAX_IMAGE_DIMENSION: int = 2000

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
    def validate_non_negative_int(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Value cannot be negative")
        return v

    @field_validator("CORS_ORIGINS", mode="after")
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
