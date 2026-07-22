"""deployment_check CLI behavior."""

from __future__ import annotations

from app.cli import deployment_check
from app.config import get_settings


def test_config_only_passes_for_test_environment(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 0
    get_settings.cache_clear()


def test_config_only_fails_staging_with_e2e(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "staging")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://helios-staging.example.vercel.app")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_staging_example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 1
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.delenv("HELIOS_E2E_TEST_MODE", raising=False)
    get_settings.cache_clear()


def test_config_only_fails_staging_with_demo_mode(monkeypatch):
    """The L1 release-candidate finding: demo mode must fail staging startup."""
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "staging")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
    monkeypatch.setenv("HELIOS_DEMO_MODE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://helios-staging.example.vercel.app")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_staging_example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 1
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.delenv("HELIOS_DEMO_MODE", raising=False)
    get_settings.cache_clear()


def test_config_only_fails_production_with_demo_mode(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "production")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
    monkeypatch.setenv("HELIOS_DEMO_MODE", "true")
    monkeypatch.setenv("CORS_ORIGINS", "https://helios.example.com")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_production_example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 1
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.delenv("HELIOS_DEMO_MODE", raising=False)
    get_settings.cache_clear()


def test_config_only_passes_staging_with_demo_mode_false(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "staging")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
    monkeypatch.setenv("HELIOS_DEMO_MODE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://helios-staging.example.vercel.app")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_staging_example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 0
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.delenv("HELIOS_DEMO_MODE", raising=False)
    get_settings.cache_clear()


def test_config_only_passes_production_with_demo_mode_false(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "production")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
    monkeypatch.setenv("HELIOS_DEMO_MODE", "false")
    monkeypatch.setenv("CORS_ORIGINS", "https://helios.example.com")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_production_example")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.example/helios")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 0
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.delenv("HELIOS_DEMO_MODE", raising=False)
    get_settings.cache_clear()


def test_config_only_passes_local_with_demo_mode_true(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "local")
    monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
    monkeypatch.setenv("HELIOS_DEMO_MODE", "true")
    get_settings.cache_clear()
    assert deployment_check.run_config_check() == 0
    get_settings.cache_clear()
    monkeypatch.setenv("HELIOS_ENVIRONMENT", "test")
    monkeypatch.delenv("HELIOS_DEMO_MODE", raising=False)
    get_settings.cache_clear()


def test_migration_check_reports_current_head():
    code = deployment_check.run_migration_check(strict=True)
    assert code == 0
