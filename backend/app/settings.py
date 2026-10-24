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

    # Approval and job hardening.
    approval_ttl_minutes: int = 240
    job_max_attempts: int = 3
    stuck_job_seconds: int = 120

    # Judge/demo controls mutate only clearly labeled TEST suppliers.
    demo_controls_enabled: bool = True

    # Evidence freshness windows: older evidence is treated as stale by the policy engine.
    ofac_evidence_ttl_hours: int = 24
    sam_evidence_ttl_hours: int = 24 * 7
    fda_evidence_ttl_hours: int = 24 * 7
    crs_evidence_ttl_hours: int = 24 * 7

    # Public-data integrations. Keyless sources need no configuration.
    http_user_agent: str = "ReliefMesh/1.0 (+https://github.com/shikharsisodia7/calhacks)"
    nasa_firms_map_key: SecretStr | None = None
    sam_gov_api_key: SecretStr | None = None
    ofac_sdn_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
    ofac_alt_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV"

    # Sponsor integrations.
    apify_api_token: SecretStr | None = None
    apify_discovery_actor: str = "compass~crawler-google-places"
    crs_api_key: SecretStr | None = None
    crs_base_url: str = "https://calhacks.crscreditapi.com"
    nessie_api_key: SecretStr | None = None
    nessie_base_url: str = "http://api.nessieisreal.com"
    elastic_url: str | None = None
    elastic_api_key: SecretStr | None = None
    elastic_index_prefix: str = "reliefmesh"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"

    # x402 paid evidence resource (Solana devnet by default; test funds only).
    x402_pay_to: str | None = None
    x402_network: str = "solana-devnet"
    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_price_usd: str = "0.01"

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
