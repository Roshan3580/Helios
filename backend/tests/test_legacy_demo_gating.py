"""Legacy/demo router gating (Checkpoint 18 — closes release-candidate finding L1).

Legacy/demo routers (projects, traces, dashboard, rag, evaluations, prompts,
datasets, demo seed) are mounted only when HELIOS_DEMO_MODE is explicitly
true, and HELIOS_DEMO_MODE=true fails startup validation in staging/
production. Canonical OTLP ingestion (/v1/otlp/traces) and canonical /v2
routes are unaffected either way.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import get_db
from app.main import create_app

_LEGACY_REQUESTS = (
    ("GET", "/v1/projects"),
    ("GET", "/v1/traces"),
    ("POST", "/v1/traces"),
    ("GET", "/v1/traces/does-not-matter"),
    ("GET", "/v1/dashboard/summary"),
    ("GET", "/v1/rag/metrics"),
    ("GET", "/v1/evaluations"),
    ("GET", "/v1/prompts"),
    ("GET", "/v1/datasets"),
    ("POST", "/v1/demo/seed"),
)

_LEGACY_OPENAPI_PATH_PREFIXES = (
    "/v1/projects",
    "/v1/traces",
    "/v1/dashboard",
    "/v1/rag",
    "/v1/evaluations",
    "/v1/prompts",
    "/v1/datasets",
    "/v1/demo",
)


def _build_client(monkeypatch, db_session, *, demo_mode: bool, environment: str = "test"):
    monkeypatch.setenv("HELIOS_DEMO_MODE", "true" if demo_mode else "false")
    monkeypatch.setenv("HELIOS_ENVIRONMENT", environment)
    get_settings.cache_clear()
    fresh_app = create_app()

    def _override():
        yield db_session

    fresh_app.dependency_overrides[get_db] = _override
    return fresh_app


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    yield
    get_settings.cache_clear()


class TestDemoModeDisabled:
    """Section 9.A — default (disabled) mounting."""

    def test_legacy_routes_absent(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        with TestClient(fresh_app) as c:
            for method, path in _LEGACY_REQUESTS:
                response = c.request(method, path)
                assert response.status_code == 404, f"{method} {path}"

    def test_legacy_routes_absent_from_openapi(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        with TestClient(fresh_app) as c:
            schema = c.get("/openapi.json").json()
        paths = schema["paths"].keys()
        for prefix in _LEGACY_OPENAPI_PATH_PREFIXES:
            assert not any(p.startswith(prefix) for p in paths), prefix

    def test_default_settings_resolve_demo_mode_false(self, monkeypatch):
        monkeypatch.delenv("HELIOS_DEMO_MODE", raising=False)
        monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
        get_settings.cache_clear()
        assert get_settings().helios_demo_mode is False


class TestDemoModeEnabled:
    """Section 9.B — explicit enablement in an allowed environment."""

    def test_legacy_routes_mounted(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=True)
        with TestClient(fresh_app) as c:
            assert c.get("/v1/projects").status_code == 200
            assert c.get("/v1/traces").status_code == 200
            assert c.get("/v1/dashboard/summary").status_code == 200
            assert c.get("/v1/rag/metrics").status_code == 200
            assert c.get("/v1/evaluations").status_code == 200
            assert c.get("/v1/prompts").status_code == 200
            assert c.get("/v1/datasets").status_code == 200
            # Existing demo-seed behavior (403 unless helios_demo_mode) is
            # preserved; here it is true, so seeding proceeds.
            seed = c.post("/v1/demo/seed")
            assert seed.status_code == 200

    def test_legacy_routes_present_in_openapi(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=True)
        with TestClient(fresh_app) as c:
            schema = c.get("/openapi.json").json()
        paths = schema["paths"].keys()
        for prefix in _LEGACY_OPENAPI_PATH_PREFIXES:
            assert any(p.startswith(prefix) for p in paths), prefix

    def test_canonical_routes_remain_mounted(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=True)
        with TestClient(fresh_app) as c:
            assert c.get("/v2/traces").status_code == 401
            assert c.get("/health/live").status_code == 200


class TestCanonicalOtlpPreservation:
    """Section 9.C — canonical OTLP ingestion is never gated by demo mode."""

    def test_otlp_route_exists_when_demo_disabled(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        with TestClient(fresh_app) as c:
            response = c.post(
                "/v1/otlp/traces",
                content=b"",
                headers={"content-type": "application/x-protobuf"},
            )
        # Missing credentials -> 401 (route reached), never 404 (route absent).
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    def test_otlp_in_openapi_when_demo_disabled(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        with TestClient(fresh_app) as c:
            schema = c.get("/openapi.json").json()
        assert "/v1/otlp/traces" in schema["paths"]

    def test_valid_ingest_still_works_when_demo_disabled(
        self, monkeypatch, db_session, make_api_key
    ):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        key = make_api_key(project_slug="gating-otlp")
        with TestClient(fresh_app) as c:
            from otlp_helpers import make_request, make_span, post_otlp

            response = post_otlp(c, make_request([make_span()]), token=key.token)
        assert response.status_code == 200


class TestV2Preservation:
    """Section 9.D — authenticated /v2 routes are never gated by demo mode."""

    def test_user_v2_mounted_when_demo_disabled(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        with TestClient(fresh_app) as c:
            response = c.get("/v2/user/me")
        # Route exists (missing/invalid JWT -> 401), not 404.
        assert response.status_code == 401

    def test_machine_v2_traces_mounted_when_demo_disabled(self, monkeypatch, db_session):
        fresh_app = _build_client(monkeypatch, db_session, demo_mode=False)
        with TestClient(fresh_app) as c:
            response = c.get("/v2/traces")
        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"


class TestUnsafeEnvironments:
    """Section 9.E — staging/production reject demo mode; local allows it."""

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_demo_mode_true_fails_startup(self, monkeypatch, db_session, environment):
        monkeypatch.setenv("CORS_ORIGINS", "https://helios.example.com")
        monkeypatch.setenv("WORKOS_CLIENT_ID", "client_example")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
        fresh_app = _build_client(
            monkeypatch, db_session, demo_mode=True, environment=environment
        )
        with pytest.raises(RuntimeError, match="demo_mode_forbidden"):
            with TestClient(fresh_app):
                pass

    @pytest.mark.parametrize("environment", ["staging", "production"])
    def test_demo_mode_false_allows_startup(self, monkeypatch, db_session, environment):
        monkeypatch.setenv("CORS_ORIGINS", "https://helios.example.com")
        monkeypatch.setenv("WORKOS_CLIENT_ID", "client_example")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
        fresh_app = _build_client(
            monkeypatch, db_session, demo_mode=False, environment=environment
        )
        with TestClient(fresh_app) as c:
            assert c.get("/health/live").status_code == 200

    def test_local_allows_demo_mode_true_startup(self, monkeypatch, db_session):
        fresh_app = _build_client(
            monkeypatch, db_session, demo_mode=True, environment="local"
        )
        with TestClient(fresh_app) as c:
            assert c.get("/health/live").status_code == 200
            assert c.get("/v1/projects").status_code == 200
