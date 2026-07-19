"""CORS policy unit + integration checks."""

from __future__ import annotations

from app.config import Settings
from app.cors_policy import ALLOWED_HEADERS, ALLOWED_METHODS, build_cors_kwargs


def test_local_includes_loopback_regex():
    settings = Settings(helios_environment="local", helios_e2e_test_mode=False)
    kwargs = build_cors_kwargs(settings)
    assert "allow_origin_regex" in kwargs
    assert kwargs["allow_methods"] == ALLOWED_METHODS
    assert "Authorization" in kwargs["allow_headers"]


def test_staging_excludes_loopback_regex():
    settings = Settings(
        helios_environment="staging",
        helios_e2e_test_mode=False,
        cors_origins="https://helios-staging.example.vercel.app",
    )
    kwargs = build_cors_kwargs(settings)
    assert "allow_origin_regex" not in kwargs
    assert kwargs["allow_origins"] == ["https://helios-staging.example.vercel.app"]


def test_e2e_mode_includes_loopback_even_if_env_odd():
    settings = Settings(helios_environment="local", helios_e2e_test_mode=True)
    kwargs = build_cors_kwargs(settings)
    assert "allow_origin_regex" in kwargs


def test_preflight_allows_authorization_for_local_origin(client):
    response = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code in {200, 204}
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    allow_headers = response.headers.get("access-control-allow-headers", "").lower()
    assert "authorization" in allow_headers


def test_hostile_origin_not_reflected(client):
    response = client.get(
        "/health/live",
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") != "https://evil.example"


def test_allowed_headers_do_not_include_wildcard():
    assert "*" not in ALLOWED_HEADERS
    assert "*" not in ALLOWED_METHODS
