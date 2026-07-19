"""E2E backend seam: disabled by default; loopback + flag required."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.config import Settings, get_settings
from app.routers import e2e as e2e_router


@pytest.fixture
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_e2e_router_absent_by_default(client):
    response = client.post(
        "/v2/e2e/seed-insights",
        json={"project_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404


def test_assert_e2e_backend_allowed_rejects_non_loopback(
    monkeypatch, clear_settings_cache
):
    settings = Settings(
        helios_e2e_test_mode=True,
        workos_issuer="https://api.workos.com/user_management/x",
        workos_jwks_url="https://api.workos.com/sso/jwks/x",
    )
    monkeypatch.setattr(e2e_router, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as exc:
        e2e_router.assert_e2e_backend_allowed()
    assert exc.value.status_code == 404


def test_assert_e2e_backend_allowed_rejects_when_disabled(
    monkeypatch, clear_settings_cache
):
    settings = Settings(helios_e2e_test_mode=False)
    monkeypatch.setattr(e2e_router, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as exc:
        e2e_router.assert_e2e_backend_allowed()
    assert exc.value.status_code == 404


def test_assert_e2e_rejects_openai_key(monkeypatch, clear_settings_cache):
    settings = Settings(
        helios_e2e_test_mode=True,
        workos_issuer="http://127.0.0.1:55/",
        workos_jwks_url="http://127.0.0.1:55/jwks",
        openai_api_key="sk-test",
    )
    monkeypatch.setattr(e2e_router, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as exc:
        e2e_router.assert_e2e_backend_allowed()
    assert exc.value.status_code == 404


def test_assert_e2e_allows_loopback(monkeypatch, clear_settings_cache):
    settings = Settings(
        helios_e2e_test_mode=True,
        workos_issuer="http://127.0.0.1:55/",
        workos_jwks_url="http://127.0.0.1:55/jwks",
    )
    monkeypatch.setattr(e2e_router, "get_settings", lambda: settings)
    e2e_router.assert_e2e_backend_allowed()
