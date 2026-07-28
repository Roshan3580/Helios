"""Checkpoint 28: hosted human-auth rejection diagnostics must be VISIBLE and SAFE.

Checkpoint 25 added safe reason codes, but they never appeared in hosted logs.
Render starts the app with plain ``uvicorn app.main:app``, and uvicorn's
``LOGGING_CONFIG`` declares only ``uvicorn``/``uvicorn.error``/``uvicorn.access``
with no ``root`` key — so the root logger kept Python's defaults (level WARNING,
no handlers), ``helios.auth.human`` inherited WARNING, and every
``logger.info(...)`` rejection record was discarded at the call site.

Critically, the Checkpoint 25 tests could not have caught this: their capture
helper calls ``logger.setLevel(logging.INFO)`` and attaches its own handler,
which manufactures exactly the conditions that were missing in production.

These tests therefore assert visibility under the REAL hosted logging
configuration (uvicorn's dictConfig, untouched root) as well as safety.

Only synthetic keys, tokens, and identifiers appear here. Nothing contacts
WorkOS.
"""

from __future__ import annotations

import logging
import logging.config
import sys

import pytest
import uvicorn.config

from app.logging_config import (
    AUTH_LOGGER_NAME,
    SafeAuthFormatter,
    configure_auth_logging,
)
from app.security import human_dependencies
from app.security.human_dependencies import SAFE_REASONS, _REASON_CODES, _reason_code
from workos_helpers import (
    DEFAULT_ORG,
    DEFAULT_SID,
    DEFAULT_SUB,
    TEST_CLIENT_ID,
    bearer,
    make_token,
    make_token_with_wrong_key,
)


# ---------------------------------------------------------------------------
# Capture helpers
# ---------------------------------------------------------------------------


class _ListHandler(logging.Handler):
    """Captures records at the level the hosted handler uses."""

    def __init__(self, level: int = logging.INFO) -> None:
        super().__init__(level=level)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture()
def hosted_logging():
    """Reproduce the hosted logging environment exactly, then observe it.

    Applies uvicorn's own ``LOGGING_CONFIG`` (as ``uvicorn app.main:app`` does),
    deliberately does NOT touch the root logger or force a level on the auth
    logger, and calls the production ``configure_auth_logging()``. A capture
    handler is attached at NOTSET so it records whatever the logger actually
    lets through — it never widens the level itself.
    """
    logger = logging.getLogger(AUTH_LOGGER_NAME)
    saved = {
        "level": logger.level,
        "propagate": logger.propagate,
        "handlers": list(logger.handlers),
        "disabled": logger.disabled,
        "global_disable": logging.root.manager.disable,
        "root_level": logging.root.level,
        "root_handlers": list(logging.root.handlers),
    }
    logging.disable(logging.NOTSET)
    logger.disabled = False

    # Exactly what uvicorn does at startup. Note: no "root" key, so the root
    # logger is left at Python's defaults.
    logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
    configure_auth_logging()

    capture = _ListHandler(level=logging.NOTSET)
    logger.addHandler(capture)
    try:
        yield capture
    finally:
        logger.handlers = saved["handlers"]
        logger.setLevel(saved["level"])
        logger.propagate = saved["propagate"]
        logger.disabled = saved["disabled"]
        logging.disable(saved["global_disable"])
        logging.root.setLevel(saved["root_level"])
        logging.root.handlers = saved["root_handlers"]


def rejection_lines(capture: _ListHandler) -> list[str]:
    return [
        r.getMessage()
        for r in capture.records
        if "human auth rejected:" in r.getMessage()
    ]


def field(line: str, name: str) -> str:
    return line.split(f"{name}=", 1)[1].split(" ", 1)[0]


def all_text(capture: _ListHandler) -> str:
    """Every record rendered through the PRODUCTION formatter.

    Using the real formatter means the assertions below cover what actually
    reaches the hosted stream, including anything a formatter might append.
    """
    formatter = SafeAuthFormatter("%(levelname)s [%(name)s] %(message)s")
    return "\n".join(formatter.format(r) for r in capture.records)


# ---------------------------------------------------------------------------
# The root-cause regression: visibility under the real hosted configuration
# ---------------------------------------------------------------------------


class TestHostedVisibility:
    def test_configure_auth_logging_does_not_touch_the_root_logger(self):
        """Guards the scope of the fix: no global logging configuration, no DEBUG.

        Asserted as a delta rather than an absolute empty state: in-process,
        pytest's logging plugin and Alembic's ``fileConfig`` both attach root
        handlers, so only the change *we* cause is meaningful.
        """
        before_handlers = list(logging.root.handlers)
        before_level = logging.root.level
        configure_auth_logging()
        assert logging.root.handlers == before_handlers
        assert logging.root.level == before_level
        # Never enables DEBUG anywhere.
        assert logging.getLogger(AUTH_LOGGER_NAME).level == logging.INFO
        assert logging.root.level != logging.DEBUG

    def test_uvicorn_config_alone_leaves_root_unconfigured(self):
        """Documents the root cause in executable form.

        uvicorn's LOGGING_CONFIG has no ``root`` key, which is precisely why an
        unconfigured ``helios.*`` logger inherited WARNING and dropped INFO.
        """
        assert "root" not in uvicorn.config.LOGGING_CONFIG
        assert set(uvicorn.config.LOGGING_CONFIG["loggers"]) == {
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
        }

    def test_rejection_is_visible_at_the_effective_hosted_level(
        self, client, workos_verifier, hosted_logging
    ):
        """The exact regression: INFO was dropped; the record must now survive."""
        logger = logging.getLogger(AUTH_LOGGER_NAME)
        response = client.get("/v2/user/me")
        assert response.status_code == 401
        lines = rejection_lines(hosted_logging)
        assert len(lines) == 1
        # Emitted at WARNING, so it clears Python's default root threshold even
        # if configure_auth_logging() never ran.
        record = [r for r in hosted_logging.records if "human auth rejected:" in r.getMessage()][0]
        assert record.levelno >= logging.WARNING
        # And it would still be enabled with no explicit level at all.
        assert logger.isEnabledFor(logging.WARNING)

    def test_rejection_survives_without_configure_auth_logging(self, monkeypatch):
        """Defense in depth: WARNING clears the default threshold on its own.

        Simulates an entrypoint that never calls configure_auth_logging(): the
        logger has no explicit level and no handler, exactly as before this
        checkpoint. An INFO record would be discarded here; a WARNING is not.
        """
        logging.config.dictConfig(uvicorn.config.LOGGING_CONFIG)
        logger = logging.getLogger(AUTH_LOGGER_NAME)
        saved_level, saved_handlers, saved_prop = (
            logger.level,
            list(logger.handlers),
            logger.propagate,
        )
        try:
            logger.setLevel(logging.NOTSET)  # inherit from root, as before the fix
            logger.handlers = []
            logger.propagate = True
            assert logger.getEffectiveLevel() == logging.WARNING
            assert not logger.isEnabledFor(logging.INFO)  # the old bug
            assert logger.isEnabledFor(logging.WARNING)  # the new guarantee
        finally:
            logger.setLevel(saved_level)
            logger.handlers = saved_handlers
            logger.propagate = saved_prop

    def test_configuration_is_idempotent_across_many_apps(self):
        """Tests build many apps; handlers must never stack (no duplicate lines)."""
        logger = configure_auth_logging()
        before = len(logger.handlers)
        for _ in range(5):
            configure_auth_logging()
        assert len(logger.handlers) == before

    def test_propagation_disabled_so_records_cannot_duplicate(self):
        logger = configure_auth_logging()
        assert logger.propagate is False

    def test_one_rejection_emits_exactly_one_diagnostic_record(
        self, client, workos_verifier, hosted_logging
    ):
        client.get("/v2/user/me", headers=bearer(make_token(expires_in=-30)))
        assert len(rejection_lines(hosted_logging)) == 1

    def test_machine_api_key_logger_visibility_is_unchanged(self):
        """Scope guard: the parent `helios.auth` (project API keys) is untouched.

        Its INFO records include internal key ids; configuring the parent would
        newly expose them in hosted logs.
        """
        configure_auth_logging()
        parent = logging.getLogger("helios.auth")
        assert parent.level == logging.NOTSET  # no explicit level set by us
        assert parent.handlers == []
        assert parent.propagate is True


# ---------------------------------------------------------------------------
# Reason allowlist
# ---------------------------------------------------------------------------


class TestReasonAllowlist:
    @pytest.mark.parametrize(
        ("internal", "expected"),
        [
            ("missing_token", "auth_missing_token"),
            ("expired_jwt", "auth_expired_token"),
            ("wrong_issuer", "auth_invalid_issuer"),
            ("missing_client_id", "auth_invalid_client_id"),
            ("wrong_client_id", "auth_invalid_client_id"),
            ("invalid_signature", "auth_invalid_signature"),
            ("unknown_signing_key", "auth_invalid_signature"),
            ("unsupported_algorithm", "auth_invalid_signature"),
            ("missing_kid", "auth_invalid_signature"),
            ("malformed_jwt", "auth_invalid_signature"),
            ("jwks_unavailable", "auth_jwks_failure"),
            ("missing_org", "auth_missing_org"),
            ("organization_unavailable", "auth_missing_org"),
            ("human_auth_not_configured", "auth_not_configured"),
            ("missing_claims", "auth_invalid_token"),
            ("missing_sub", "auth_missing_subject"),
            ("missing_sid", "auth_invalid_token"),
        ],
    )
    def test_each_internal_reason_maps_to_expected_safe_code(self, internal, expected):
        assert _reason_code(internal) == expected

    @pytest.mark.parametrize(
        "unknown",
        [
            "",
            "totally_new_reason",
            "database url postgresql://u:p@h/db",
            "Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig",
            "client_test_helios",
        ],
    )
    def test_unknown_reason_collapses_to_auth_rejected(self, unknown):
        """A raw internal reason can never reach a log line unmapped."""
        assert _reason_code(unknown) == "auth_rejected"

    def test_every_mapping_target_is_on_the_allowlist(self):
        assert set(_REASON_CODES.values()) <= SAFE_REASONS

    def test_required_reason_codes_are_all_preserved(self):
        required = {
            "auth_missing_token",
            "auth_expired_token",
            "auth_invalid_issuer",
            "auth_invalid_client_id",
            "auth_invalid_signature",
            "auth_jwks_failure",
            "auth_missing_org",
            "auth_not_configured",
            "auth_invalid_token",
            "auth_missing_subject",
            "auth_rejected",
        }
        assert required == SAFE_REASONS

    def test_reason_code_output_is_always_on_the_allowlist(self):
        candidates = list(_REASON_CODES) + ["", "x", "unmapped", "AUTH_REJECTED"]
        for candidate in candidates:
            assert _reason_code(candidate) in SAFE_REASONS


# ---------------------------------------------------------------------------
# Route path handling
# ---------------------------------------------------------------------------


class TestRoutePath:
    def test_route_path_is_logged(self, client, workos_verifier, hosted_logging):
        client.get("/v2/user/me")
        line = rejection_lines(hosted_logging)[0]
        assert field(line, "path") == "/v2/user/me"

    def test_org_route_path_is_logged(self, client, workos_verifier, hosted_logging):
        client.get("/v2/user/projects", headers=bearer(make_token(org_id=None)))
        line = rejection_lines(hosted_logging)[0]
        assert field(line, "path") == "/v2/user/projects"

    def test_query_string_is_never_logged(self, client, workos_verifier, hosted_logging):
        secret_qs = "token=eyJhbGciOiJSUzI1NiJ9.abc.def&api_key=hel_proj_leak123456"
        client.get(f"/v2/user/me?{secret_qs}")
        text = all_text(hosted_logging)
        assert "/v2/user/me" in text
        for fragment in ("?", "token=", "api_key=", "hel_proj_leak123456", "eyJ"):
            assert fragment not in text

    def test_line_shape_is_exactly_the_hosted_contract(
        self, client, workos_verifier, hosted_logging
    ):
        client.get("/v2/user/me")
        line = rejection_lines(hosted_logging)[0]
        assert line == "human auth rejected: reason=auth_missing_token status=401 path=/v2/user/me"

    def test_status_is_only_401_or_403(self, client, workos_verifier, hosted_logging):
        client.get("/v2/user/me")  # 401
        client.get("/v2/user/projects", headers=bearer(make_token(org_id=None)))  # 403
        statuses = {field(line, "status") for line in rejection_lines(hosted_logging)}
        assert statuses == {"401", "403"}

    def test_missing_request_degrades_safely(self):
        """A direct dependency call without a Request must not raise."""
        assert human_dependencies._safe_path(None) == "-"


# ---------------------------------------------------------------------------
# Leakage: nothing sensitive may reach the stream
# ---------------------------------------------------------------------------


SENSITIVE_SUBSTRINGS = (
    "eyJ",  # any JWT segment
    "Bearer ",
    "bearer ",
    "authorization",
    "Authorization",
    "Cookie",
    "cookie",
    TEST_CLIENT_ID,
    DEFAULT_SUB,
    DEFAULT_SID,
    DEFAULT_ORG,
    "api.workos.com",
    "jwks",
    "sso_oidc_key",
    "postgresql://",
    "@example.com",
)


class TestNoLeakage:
    @pytest.mark.parametrize(
        "case",
        ["missing", "expired", "wrong_signature", "wrong_client_id", "missing_org"],
    )
    def test_no_sensitive_material_in_any_rejection(
        self, client, workos_verifier, hosted_logging, case
    ):
        if case == "missing":
            client.get("/v2/user/me")
            token = None
        elif case == "expired":
            token = make_token(expires_in=-30)
            client.get("/v2/user/me", headers=bearer(token))
        elif case == "wrong_signature":
            token = make_token_with_wrong_key()
            client.get("/v2/user/me", headers=bearer(token))
        elif case == "wrong_client_id":
            token = make_token(client_id="client_some_other_app")
            client.get("/v2/user/me", headers=bearer(token))
        else:
            token = make_token(org_id=None)
            client.get("/v2/user/projects", headers=bearer(token))

        text = all_text(hosted_logging)
        assert rejection_lines(hosted_logging), "expected a diagnostic line"
        if token:
            assert token not in text
            for segment in token.split("."):
                if len(segment) > 12:
                    assert segment not in text
        for fragment in SENSITIVE_SUBSTRINGS:
            assert fragment not in text, f"leaked {fragment!r}"

    def test_authorization_header_value_is_never_logged(
        self, client, workos_verifier, hosted_logging
    ):
        token = make_token()
        header = bearer(token)
        client.get("/v2/user/me", headers={**header, "Cookie": "wos-session=abc123def456"})
        text = all_text(hosted_logging)
        for value in list(header.values()) + ["wos-session", "abc123def456"]:
            assert value not in text

    def test_non_bearer_scheme_logs_a_safe_reason_without_the_header(
        self, client, workos_verifier, hosted_logging
    ):
        client.get("/v2/user/me", headers={"Authorization": "Basic dXNlcjpwYXNzd29yZA=="})
        lines = rejection_lines(hosted_logging)
        assert len(lines) == 1
        assert field(lines[0], "reason") == "auth_missing_token"
        text = all_text(hosted_logging)
        for fragment in ("Basic", "dXNlcjpwYXNzd29yZA=="):
            assert fragment not in text

    def test_exception_detail_is_dropped_structurally(self):
        """Even exc_info=True cannot put exception text on the stream."""
        formatter = SafeAuthFormatter("%(levelname)s %(message)s")
        try:
            raise ValueError("postgresql://user:pw@host/db leaked via exception")
        except ValueError:
            record = logging.LogRecord(
                name=AUTH_LOGGER_NAME,
                level=logging.WARNING,
                pathname=__file__,
                lineno=1,
                msg="human auth rejected: reason=auth_rejected status=401 path=/v2/user/me",
                args=(),
                exc_info=sys.exc_info(),
            )
            rendered = formatter.format(record)
        assert "postgresql://" not in rendered
        assert "ValueError" not in rendered
        assert "Traceback" not in rendered
        assert rendered.endswith("path=/v2/user/me")

    def test_stack_info_is_dropped_structurally(self):
        formatter = SafeAuthFormatter("%(message)s")
        record = logging.LogRecord(
            name=AUTH_LOGGER_NAME,
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="human auth rejected: reason=auth_rejected status=401 path=/x",
            args=(),
            exc_info=None,
        )
        record.stack_info = 'File "secret.py", line 1, in leak'
        rendered = formatter.format(record)
        assert "secret.py" not in rendered

    def test_no_exc_info_is_passed_by_the_auth_boundary(
        self, client, workos_verifier, hosted_logging
    ):
        client.get("/v2/user/me", headers=bearer(make_token_with_wrong_key()))
        for record in hosted_logging.records:
            assert record.exc_info is None
            assert getattr(record, "stack_info", None) is None


# ---------------------------------------------------------------------------
# Client-facing responses must be unchanged
# ---------------------------------------------------------------------------


class TestClientResponsesUnchanged:
    def test_generic_401_body_and_header_unchanged(self, client, workos_verifier):
        response = client.get("/v2/user/me", headers=bearer(make_token_with_wrong_key()))
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid authentication credentials"}
        assert response.headers["www-authenticate"] == "Bearer"

    def test_generic_403_body_unchanged(self, client, workos_verifier):
        response = client.get("/v2/user/projects", headers=bearer(make_token(org_id=None)))
        assert response.status_code == 403
        assert response.json() == {
            "detail": (
                "you are not a member of a Helios workspace yet; "
                "create or join a workspace to continue"
            )
        }

    @pytest.mark.parametrize("path", ["/v2/user/me", "/v2/user/projects"])
    def test_no_reason_code_is_ever_returned_to_the_client(
        self, client, workos_verifier, path
    ):
        body = client.get(path, headers=bearer(make_token_with_wrong_key())).text
        for reason in SAFE_REASONS:
            assert reason not in body
        for fragment in ("reason=", "issuer", "jwks", "client_id", "path="):
            assert fragment not in body

    def test_missing_token_401_is_still_generic(self, client, workos_verifier):
        response = client.get("/v2/user/me")
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid authentication credentials"}
