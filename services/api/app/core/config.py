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
