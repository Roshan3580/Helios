"""Checkpoint 28: the startup human-auth contract line.

One non-secret line per worker startup tells a hosted operator whether the
verifier is configured and whether the issuer/JWKS were derived or explicitly
overridden — without revealing the Client ID value, the issuer URL, the JWKS URL,
a hostname, or any credential.

Only synthetic configuration values appear here. Nothing contacts WorkOS.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from app.config import (
    ISSUER_MODE_DERIVED,
    ISSUER_MODE_EXPLICIT,
    ISSUER_MODE_MULTI_APPLICATION,
    get_settings,
)
from app.logging_config import AUTH_LOGGER_NAME, SafeAuthFormatter
from app.main import create_app, log_auth_contract

# Synthetic values chosen so a leak would be unmistakable in an assertion.
FAKE_CLIENT_ID = "client_synthetic_never_real_0001"
FAKE_ISSUER = "https://synthetic-issuer.invalid"
FAKE_JWKS_URL = "https://synthetic-issuer.invalid/sso/jwks/client_synthetic_never_real_0001"


class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def auth_logs():
    logger = logging.getLogger(AUTH_LOGGER_NAME)
    saved_level, saved_disabled = logger.level, logger.disabled
    saved_global = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.INFO)
    capture = _Capture()
    logger.addHandler(capture)
    try:
        yield capture
    finally:
        logger.removeHandler(capture)
        logger.setLevel(saved_level)
        logger.disabled = saved_disabled
        logging.disable(saved_global)


def contract_lines(capture: _Capture) -> list[str]:
    return [
        r.getMessage()
        for r in capture.records
        if "human auth verifier configured:" in r.getMessage()
    ]


def rendered(capture: _Capture) -> str:
    formatter = SafeAuthFormatter("%(levelname)s [%(name)s] %(message)s")
    return "\n".join(formatter.format(r) for r in capture.records)


def field(line: str, name: str) -> str:
    return line.split(f"{name}=", 1)[1].split(" ", 1)[0]


class _Settings:
    """Minimal settings stand-in; only the four attributes the log line reads."""

    def __init__(
        self,
        *,
        client_id="",
        issuer_client_id="",
        issuer="",
        jwks_url="",
        environment="staging",
    ):
        self.workos_client_id = client_id
        self.workos_issuer_client_id = issuer_client_id
        self.workos_issuer = issuer
        self.workos_jwks_url = jwks_url
        self.helios_environment = environment

    @property
    def workos_issuer_mode(self):
        if self.workos_issuer:
            return ISSUER_MODE_EXPLICIT
        if self.workos_issuer_client_id:
            return ISSUER_MODE_MULTI_APPLICATION
        return ISSUER_MODE_DERIVED


class TestStartupContractContent:
    def test_reports_presence_and_derived_modes(self, auth_logs):
        log_auth_contract(_Settings(client_id=FAKE_CLIENT_ID))
        line = contract_lines(auth_logs)[0]
        assert field(line, "client_id_present") == "true"
        assert field(line, "issuer_client_id_present") == "false"
        assert field(line, "issuer_mode") == "derived_standard_set"
        assert field(line, "jwks_mode") == "derived"
        assert field(line, "environment") == "staging"

    def test_reports_explicit_modes_when_overridden(self, auth_logs):
        log_auth_contract(
            _Settings(client_id=FAKE_CLIENT_ID, issuer=FAKE_ISSUER, jwks_url=FAKE_JWKS_URL)
        )
        line = contract_lines(auth_logs)[0]
        assert field(line, "issuer_mode") == "explicit"
        assert field(line, "jwks_mode") == "explicit"

    def test_reports_multi_application_mode_without_identifiers(self, auth_logs):
        log_auth_contract(
            _Settings(client_id=FAKE_CLIENT_ID, issuer_client_id=FAKE_CLIENT_ID)
        )
        line = contract_lines(auth_logs)[0]
        assert field(line, "client_id_present") == "true"
        assert field(line, "issuer_client_id_present") == "true"
        assert field(line, "issuer_mode") == "multi_application"
        assert FAKE_CLIENT_ID not in rendered(auth_logs)

    def test_reports_absent_client_id(self, auth_logs):
        log_auth_contract(_Settings(client_id=""))
        assert field(contract_lines(auth_logs)[0], "client_id_present") == "false"

    def test_mixed_modes_are_reported_independently(self, auth_logs):
        log_auth_contract(_Settings(client_id=FAKE_CLIENT_ID, issuer=FAKE_ISSUER))
        line = contract_lines(auth_logs)[0]
        assert field(line, "issuer_mode") == "explicit"
        assert field(line, "jwks_mode") == "derived"

    def test_derived_mode_label_names_the_mode_without_the_issuer_set(self, auth_logs):
        log_auth_contract(_Settings(client_id=FAKE_CLIENT_ID))
        text = rendered(auth_logs)
        assert "issuer_mode=derived_standard_set" in text
        for fragment in ("api.workos.com", "https://", "workos.com", "user_management"):
            assert fragment not in text

    def test_never_reveals_values_hostnames_or_urls(self, auth_logs):
        log_auth_contract(
            _Settings(client_id=FAKE_CLIENT_ID, issuer=FAKE_ISSUER, jwks_url=FAKE_JWKS_URL)
        )
        text = rendered(auth_logs)
        for secret in (
            FAKE_CLIENT_ID,
            FAKE_ISSUER,
            FAKE_JWKS_URL,
            "synthetic-issuer.invalid",
            "https://",
            "sso/jwks",
            "client_synthetic",
        ):
            assert secret not in text, f"leaked {secret!r}"

    def test_line_shape_is_booleans_and_modes_only(self, auth_logs):
        log_auth_contract(_Settings(client_id=FAKE_CLIENT_ID))
        assert contract_lines(auth_logs)[0] == (
            "human auth verifier configured: client_id_present=true "
            "issuer_client_id_present=false issuer_mode=derived_standard_set "
            "jwks_mode=derived environment=staging"
        )

    def test_never_raises_on_broken_settings(self, auth_logs):
        """Readiness must never depend on this diagnostic."""

        class Broken:
            @property
            def workos_client_id(self):
                raise RuntimeError("boom")

        log_auth_contract(Broken())  # must not propagate
        assert contract_lines(auth_logs) == []


class TestStartupContractLifecycle:
    def _app_with(self, monkeypatch, environment, *, issuer_client_id=None):
        monkeypatch.setenv("HELIOS_ENVIRONMENT", environment)
        monkeypatch.setenv("WORKOS_CLIENT_ID", FAKE_CLIENT_ID)
        monkeypatch.delenv("WORKOS_ISSUER_CLIENT_ID", raising=False)
        monkeypatch.delenv("WORKOS_ISSUER", raising=False)
        monkeypatch.delenv("WORKOS_JWKS_URL", raising=False)
        if issuer_client_id is not None:
            monkeypatch.setenv("WORKOS_ISSUER_CLIENT_ID", issuer_client_id)
        monkeypatch.setenv("HELIOS_DEMO_MODE", "false")
        monkeypatch.setenv("HELIOS_E2E_TEST_MODE", "false")
        monkeypatch.setenv(
            "CORS_ORIGINS", "https://helios-startup-contract-test.invalid"
        )
        # Staging validation correctly refuses a DATABASE_URL pointing at the
        # isolated test database. That guard is load-bearing and must not be
        # weakened, so these startup-only tests present a synthetic non-test URL.
        # Nothing connects: the SQLAlchemy engine was already built at import
        # time from the real test URL, and the routes exercised here
        # (/health/live) have no database dependency.
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://synthetic:synthetic@db.invalid:5432/helios_startup_contract",
        )
        get_settings.cache_clear()
        return create_app()

    def test_emitted_exactly_once_per_app_startup(self, monkeypatch, auth_logs):
        try:
            app = self._app_with(monkeypatch, "staging")
            with TestClient(app):
                pass
            assert len(contract_lines(auth_logs)) == 1
        finally:
            get_settings.cache_clear()

    def test_not_emitted_in_local_environments(self, monkeypatch, auth_logs):
        try:
            app = self._app_with(monkeypatch, "local")
            with TestClient(app):
                pass
            assert contract_lines(auth_logs) == []
        finally:
            get_settings.cache_clear()

    def test_multi_application_mode_emitted_once_without_values(
        self, monkeypatch, auth_logs
    ):
        try:
            app = self._app_with(
                monkeypatch,
                "staging",
                issuer_client_id="client_synthetic_default_0001",
            )
            with TestClient(app):
                pass
            line = contract_lines(auth_logs)[0]
            assert "issuer_client_id_present=true" in line
            assert "issuer_mode=multi_application" in line
            assert "client_synthetic_default_0001" not in rendered(auth_logs)
        finally:
            get_settings.cache_clear()

    def test_no_loop_across_many_requests(self, monkeypatch, auth_logs):
        """The line belongs to startup, not the request path."""
        try:
            app = self._app_with(monkeypatch, "staging")
            with TestClient(app) as client:
                for _ in range(5):
                    client.get("/health/live")
            assert len(contract_lines(auth_logs)) == 1
        finally:
            get_settings.cache_clear()

    def test_startup_validation_remains_fail_closed(self, monkeypatch, auth_logs):
        """A staging contract violation must still abort startup.

        The diagnostic line must not have converted a fatal misconfiguration into
        a mere log message: demo mode in staging is forbidden.
        """
        monkeypatch.setenv("HELIOS_ENVIRONMENT", "staging")
        monkeypatch.setenv("WORKOS_CLIENT_ID", FAKE_CLIENT_ID)
        monkeypatch.delenv("WORKOS_ISSUER_CLIENT_ID", raising=False)
        monkeypatch.delenv("WORKOS_ISSUER", raising=False)
        monkeypatch.delenv("WORKOS_JWKS_URL", raising=False)
        monkeypatch.setenv("HELIOS_DEMO_MODE", "true")  # forbidden in staging
        monkeypatch.setenv("CORS_ORIGINS", "https://helios-startup-contract-test.invalid")
        monkeypatch.setenv(
            "DATABASE_URL",
            "postgresql://synthetic:synthetic@db.invalid:5432/helios_startup_contract",
        )
        get_settings.cache_clear()
        try:
            app = create_app()
            with pytest.raises(RuntimeError, match="deployment contract failed"):
                with TestClient(app):
                    pass
            # Aborted before the diagnostic line was emitted.
            assert contract_lines(auth_logs) == []
        finally:
            get_settings.cache_clear()
