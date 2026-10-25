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
    # Optional regex for preview deployments, e.g. https://reliefmesh-[a-z0-9-]+\.vercel\.app
    cors_origin_regex: str | None = None
    resend_api_key: SecretStr | None = None
    # The sending domain lives only here (env RELIEFMESH_EMAIL_FROM); it must be a domain verified in Resend.
    email_from: str = "ReliefMesh Procurement <procurement@reliefmesh.example>"
    expose_invitation_links: bool = False
    auth_rate_limit_per_minute: int = 12

    # Approval and job hardening.
    approval_ttl_minutes: int = 240
    job_max_attempts: int = 3
    stuck_job_seconds: int = 120

    # Demo/judge tooling: seeded TEST suppliers with synthetic quotes, simulated disruptions, and the
    # demo-org self-approval override. Off unless explicitly enabled; production refuses to start with it.
    demo_mode: bool = False
    # Agent chat senders allowed to spend paid credits (Apify discovery). Empty denies every agent sender.
    agent_privileged_senders: list[str] = []

    # Evidence freshness windows: older evidence is treated as stale by the policy engine.
    ofac_evidence_ttl_hours: int = 24
    sam_evidence_ttl_hours: int = 24 * 7
    fda_evidence_ttl_hours: int = 24 * 7
    crs_evidence_ttl_hours: int = 24 * 7

    # Public-data integrations. Keyless sources need no configuration.
    http_user_agent: str = "ReliefMesh/1.0 (+https://reliefmesh.us)"
    nasa_firms_map_key: SecretStr | None = None
    sam_gov_api_key: SecretStr | None = None
    ofac_sdn_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV"
    ofac_alt_url: str = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV"

    # Sponsor integrations.
    apify_api_token: SecretStr | None = None
    apify_discovery_actor: str = "compass~crawler-google-places"
    crs_username: SecretStr | None = None
    crs_password: SecretStr | None = None
    crs_base_url: str = "https://api-sandbox.stitchcredit.com/api"
    nessie_api_key: SecretStr | None = None
    nessie_base_url: str = "http://api.nessieisreal.com"
    elastic_url: str | None = None
    elastic_api_key: SecretStr | None = None
    elastic_index_prefix: str = "reliefmesh"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash"  # free tier, ~4 s; 2.5 is closed to new projects, 3.8 takes 60 s+
    quote_draft_per_minute: int = 6

    # x402 paid evidence resource (Solana devnet by default; test funds only).
    x402_pay_to: str | None = None
    x402_network: str = "solana-devnet"
    x402_facilitator_url: str = "https://x402.org/facilitator"
    x402_price_usd: str = "0.01"
    x402_daily_cap_usd: str = "0.10"
    x402_buyer_private_key: SecretStr | None = None
    x402_treasury_private_key: SecretStr | None = None
    # Public base URL of this API (the buyer reaches the Evidence Exchange over real HTTP).
    public_api_url: str = "http://127.0.0.1:8000"

    # Operations integrations (Gmail, Google Calendar, Google Drive, Slack). All are per-organization
    # OAuth connections; these settings only identify the ReliefMesh OAuth apps.
    # disabled = never send email; test = persist the rendered email without sending; live = Gmail/Resend.
    # Unset resolves to "test" under app_env=test and "live" elsewhere (live still needs a connected transport).
    email_mode: Literal["disabled", "test", "live"] | None = None
    # Optional live-mode safety rail: only these addresses (or "@domain" suffixes) may receive email.
    email_allowed_recipients: list[str] = []
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    google_oauth_redirect_uri: str | None = None  # default: {public_api_url}/v1/integrations/google/callback
    slack_client_id: str | None = None
    slack_client_secret: SecretStr | None = None
    slack_redirect_uri: str | None = None  # default: {public_api_url}/v1/integrations/slack/callback
    # Fernet key for OAuth tokens at rest; derived from the JWT secret when unset.
    integration_encryption_key: SecretStr | None = None
    ops_delivery_max_attempts: int = 4
    ops_retry_base_seconds: float = 2.0

    @property
    def resolved_email_mode(self) -> str:
        return self.email_mode or ("test" if self.app_env == "test" else "live")

    @property
    def google_redirect_uri(self) -> str:
        return self.google_oauth_redirect_uri or f"{self.public_api_url.rstrip('/')}/v1/integrations/google/callback"

    @property
    def slack_oauth_redirect_uri(self) -> str:
        return self.slack_redirect_uri or f"{self.public_api_url.rstrip('/')}/v1/integrations/slack/callback"

    @field_validator("storage_mode")
    @classmethod
    def memory_is_non_production(cls, value: str, info):
        if value == "memory" and info.data.get("app_env") == "production":
            raise ValueError("Memory storage is forbidden in production")
        return value

    @property
    def demo_enabled(self) -> bool:
        return self.demo_mode and self.app_env != "production"

    def validate_runtime(self) -> None:
        if self.app_env == "production":
            if self.demo_mode:
                raise RuntimeError("RELIEFMESH_DEMO_MODE must be false in production (no synthetic data in prod)")
            if self.expose_invitation_links:
                raise RuntimeError("RELIEFMESH_EXPOSE_INVITATION_LINKS is a development-only setting")
            if self.storage_mode != "mongo" or not self.mongodb_uri:
                raise RuntimeError("Production requires RELIEFMESH_MONGODB_URI and MongoDB storage")
            if self.jwt_secret.get_secret_value() == "change-me-before-production":
                raise RuntimeError("Set RELIEFMESH_JWT_SECRET in production")


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_runtime()
    return settings
