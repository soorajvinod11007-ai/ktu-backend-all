from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, NoDecode


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- Runtime ---
    ENVIRONMENT: str = Field(..., description="dev | staging | prod")
    LOG_LEVEL: str = Field(default="INFO")

    # --- Database ---
    DATABASE_URL: str = Field(..., description="postgresql+psycopg://...")
    TEST_DATABASE_URL: str = Field(..., description="postgresql+psycopg://...")

    # --- Auth ---
    JWT_SECRET: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, gt=0)
    REFRESH_REUSE_GRACE_SECONDS: int = Field(default=10, ge=0)

    # --- Auth / Phase 3: password policy ---
    PASSWORD_MIN_LENGTH: int = 8

    # --- Auth / Phase 3: per-account lockout ---
    MAX_LOGIN_ATTEMPTS: int = 5
    LOGIN_LOCKOUT_MINUTES: int = 15

    # --- Auth / Phase 3: per-IP login rate limit ---
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 5
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 60

    # --- Auth / Phase 3: cleanup retention ---
    REFRESH_TOKEN_RETENTION_DAYS: int = 30

    # --- Auth / Phase 3: seed users ---
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "change-me-admin"
    ADMIN_EMAIL: str = "admin@example.com"

    PRINCIPAL_USERNAME: str = "principal"
    PRINCIPAL_PASSWORD: str = "change-me-principal"
    PRINCIPAL_EMAIL: str = "principal@example.com"

    # --- Phase 4: admin dashboard + export/import + cache -------------------
    ADMIN_PAGE_SIZE_DEFAULT: int = 25
    ADMIN_PAGE_SIZE_MAX: int = 100
    ADMIN_EXPORT_ROW_CAP: int = 50_000
    ADMIN_IMPORT_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB
    ADMIN_DASHBOARD_CACHE_SECONDS: int = 60
    ADMIN_OPTIONS_LIMIT: int = 50

    # --- HTTP / CORS ---
    # NoDecode stops pydantic-settings from trying json.loads() on the raw
    # env string; the validator below does the comma-splitting instead.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(default_factory=list)

    # --- Uploads ---
    UPLOAD_DIR: str = Field(default="./uploads")
    MAX_UPLOAD_MB: int = Field(default=20, gt=0)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("ENVIRONMENT")
    @classmethod
    def _validate_environment(cls, value: str) -> str:
        allowed = {"dev", "staging", "prod", "test"}
        if value not in allowed:
            raise ValueError(f"ENVIRONMENT must be one of {sorted(allowed)}")
        return value

    @model_validator(mode="after")
    def _validate_jwt_secret_in_prod(self) -> Settings:
        if self.ENVIRONMENT == "prod":
            if self.JWT_SECRET == "dev-only-secret-replace-me-with-32-plus-random-chars":
                raise ValueError("JWT_SECRET must not use the placeholder in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor — safe to call anywhere."""
    return Settings()  # type: ignore[call-arg]