from functools import lru_cache

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.deployment_validation import validate_settings

# Official WorkOS AuthKit access-token issuers (Checkpoint 29).
#
# WorkOS documents the AuthKit access-token issuer as the API root, and its
# current documentation presents BOTH standard spellings of that root — with and
# without a trailing slash. A hosted token carrying the trailing-slash form was
# rejected by a verifier that accepted only the no-slash form, producing
# `reason=auth_invalid_issuer` on every authenticated request despite a fully
# valid session, signature, and client_id.
#
# This is therefore a CLOSED, two-entry allowlist of exact full strings — not a
# normalization rule. Helios never strips, appends, lowercases, or otherwise
# transforms an issuer, and never derives one from token or request data. Each
# entry is compared by exact full-string equality (PyJWT membership over this
# tuple), so no prefix, suffix, subdomain, path, or wildcard match is possible:
# `https://api.workos.com/foo`, `https://api.workos.com//`,
# `https://api.workos.com/user_management/<client_id>`,
# `https://evil.api.workos.com`, and `https://api.workos.com.evil.example` all
# remain rejected.
#
# Application isolation does NOT rest on the issuer — the issuer is shared by
# every WorkOS application. It rests on the separately validated `client_id`
# claim plus the application-specific JWKS at /sso/jwks/<client_id>.
WORKOS_STANDARD_ISSUERS: tuple[str, ...] = (
    "https://api.workos.com",
    "https://api.workos.com/",
)

# Representative derived issuer, used where a single value is required (JWKS
# derivation and the deployment contract). Never used to widen acceptance.
WORKOS_DEFAULT_ISSUER = WORKOS_STANDARD_ISSUERS[0]

# Startup-diagnostic mode labels. Non-secret: they name the mode only and never
# carry an issuer value, accepted-issuer list, client id, or AuthKit domain.
ISSUER_MODE_DERIVED = "derived_standard_set"
ISSUER_MODE_EXPLICIT = "explicit"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Deployment environment: local|test|e2e|staging|production
    helios_environment: str = "local"

    database_url: str = "postgresql://helios:helios@localhost:5433/helios"
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    # Safe by default: legacy/demo routers are mounted only when this is
    # explicitly true (see app.main.create_app). Forbidden in staging/
    # production (see deployment_validation.validate_settings).
    helios_demo_mode: bool = False
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

    # Browser E2E release gate only. Disabled by default. When true, registers
    # /v2/e2e/* helpers that still require verified human JWTs and loopback JWKS.
    helios_e2e_test_mode: bool = False

    @field_validator("helios_environment")
    @classmethod
    def _normalize_environment(cls, value: str) -> str:
        return (value or "local").strip().lower()

    @field_validator("helios_analyst_provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        return (value or "").strip().lower()

    @property
    def workos_issuer_resolved(self) -> str:
        """Single representative issuer, for JWKS derivation and the contract.

        Acceptance is decided by :attr:`workos_accepted_issuers`, never by this
        value alone.
        """
        # Explicit issuer (e.g. a custom WorkOS auth domain) is used verbatim.
        if self.workos_issuer:
            return self.workos_issuer
        # Default WorkOS-hosted AuthKit: the access-token issuer is the API root.
        if self.workos_client_id:
            return WORKOS_DEFAULT_ISSUER
        return ""

    @property
    def workos_issuer_mode(self) -> str:
        """``explicit`` when WORKOS_ISSUER is set, else ``derived_standard_set``."""
        return ISSUER_MODE_EXPLICIT if self.workos_issuer else ISSUER_MODE_DERIVED

    @property
    def workos_accepted_issuers(self) -> tuple[str, ...]:
        """The exact issuer value(s) this deployment accepts.

        Two modes, and only two:

        * **Explicit** — ``WORKOS_ISSUER`` is set: accept exactly that one value,
          verbatim. A trailing slash is neither added nor removed, and the
          standard WorkOS roots are NOT additionally accepted (unless the
          configured value happens to be one of them).
        * **Derived standard** — ``WORKOS_ISSUER`` is unset: accept exactly the
          two documented WorkOS API-root spellings and nothing else.

        Never inferred from request data or from an unverified token claim.
        """
        if self.workos_issuer:
            return (self.workos_issuer,)
        if self.workos_client_id:
            return WORKOS_STANDARD_ISSUERS
        return ()

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

    def deployment_issues(self) -> list:
        return validate_settings(
            environment=self.helios_environment,
            database_url=self.database_url,
            cors_origins=self.cors_origin_list,
            workos_client_id=self.workos_client_id,
            workos_issuer=self.workos_issuer_resolved,
            workos_jwks_url=self.workos_jwks_url_resolved,
            helios_e2e_test_mode=self.helios_e2e_test_mode,
            helios_demo_mode=self.helios_demo_mode,
            narrative_enabled=self.helios_analyst_narrative_enabled,
            allow_third_party=self.helios_analyst_allow_third_party,
            analyst_provider=self.helios_analyst_provider,
            openai_key_present=bool(self.openai_api_key.get_secret_value()),
        )

    def __repr__(self) -> str:
        # Never include API-key material in settings representations.
        return (
            "Settings("
            f"helios_environment={self.helios_environment!r}, "
            "helios_analyst_narrative_enabled="
            f"{self.helios_analyst_narrative_enabled!r}, "
            f"helios_analyst_provider={self.helios_analyst_provider!r}, "
            f"helios_analyst_model={self.helios_analyst_model!r})"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
