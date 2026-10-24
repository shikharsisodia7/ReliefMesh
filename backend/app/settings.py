from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Production requires MongoDB and explicit secrets."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="RELIEFMESH_", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    # Ephemeral storage permits a no-credential local UI demo; production is always MongoDB-backed.
    storage_mode: Literal["mongo", "memory"] = "memory"
    mongodb_uri: str | None = None
    mongodb_database: str = "reliefmesh"
    jwt_secret: SecretStr = Field(default=SecretStr("change-me-before-production"))
    jwt_issuer: str = "reliefmesh-api"
    frontend_origin: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000"]
    resend_api_key: SecretStr | None = None
    email_from: str = "ReliefMesh <rfq@reliefmesh.example>"
    expose_invitation_links: bool = False
    auth_rate_limit_per_minute: int = 12
    apify_api_token: SecretStr | None = None

    @field_validator("storage_mode")
    @classmethod
    def memory_is_non_production(cls, value: str, info):
        if value == "memory" and info.data.get("app_env") == "production":
            raise ValueError("Memory storage is forbidden in production")
        return value

    def validate_runtime(self) -> None:
        if self.app_env == "production":
            if self.storage_mode != "mongo" or not self.mongodb_uri:
                raise RuntimeError("Production requires RELIEFMESH_MONGODB_URI and MongoDB storage")
            if self.jwt_secret.get_secret_value() == "change-me-before-production":
                raise RuntimeError("Set RELIEFMESH_JWT_SECRET in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
