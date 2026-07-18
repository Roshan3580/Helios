from functools import lru_cache

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
