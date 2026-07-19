from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql://helios:helios@localhost:5433/helios"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    helios_demo_mode: bool = True
    app_version: str = "0.1.0"

    # WorkOS human authentication (access-token verification only; the WorkOS
    # server API key is NOT required or used to validate access tokens).
    workos_client_id: str = ""
    # Derived from the client ID when left empty (official WorkOS defaults).
    workos_issuer: str = ""
    workos_jwks_url: str = ""
    workos_jwks_cache_ttl: int = 3600  # seconds
    workos_jwks_timeout: float = 5.0  # seconds per JWKS HTTP request

    # Optional analyst narrative (disabled by default; server-only — never VITE_*).
    # Requires BOTH helios_analyst_narrative_enabled and
    # helios_analyst_allow_third_party before any provider call is made.
    helios_analyst_narrative_enabled: bool = False
    helios_analyst_allow_third_party: bool = False
    helios_analyst_provider: str = ""
    helios_analyst_model: str = ""
    helios_analyst_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    helios_analyst_max_output_tokens: int = Field(default=1200, ge=64, le=8192)
    helios_analyst_max_evidence_bytes: int = Field(default=24000, ge=1024, le=200_000)
    helios_analyst_max_findings: int = Field(default=25, ge=1, le=200)
    openai_api_key: SecretStr = SecretStr("")

    @field_validator("helios_analyst_provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        return (value or "").strip().lower()

    @property
    def workos_issuer_resolved(self) -> str:
        if self.workos_issuer:
            return self.workos_issuer
        if self.workos_client_id:
            return f"https://api.workos.com/user_management/{self.workos_client_id}"
        return ""

    @property
    def workos_jwks_url_resolved(self) -> str:
        if self.workos_jwks_url:
            return self.workos_jwks_url
        if self.workos_client_id:
            return f"https://api.workos.com/sso/jwks/{self.workos_client_id}"
        return ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def __repr__(self) -> str:
        # Never include API-key material in settings representations.
        return (
            "Settings(helios_analyst_narrative_enabled="
            f"{self.helios_analyst_narrative_enabled!r}, "
            f"helios_analyst_provider={self.helios_analyst_provider!r}, "
            f"helios_analyst_model={self.helios_analyst_model!r})"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
