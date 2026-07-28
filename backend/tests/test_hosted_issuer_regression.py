"""Checkpoint 29: the exact hosted failure, reproduced end-to-end through routes.

Observed hosted shape (Checkpoint 28 diagnostics made it visible):

    human auth rejected: reason=auth_invalid_issuer status=401 path=/v2/user/me
    human auth rejected: reason=auth_invalid_issuer status=401 path=/v2/user/projects

Everything about the request was valid — WorkOS session, signature from the
application JWKS, `client_id`, `org_id` — except that the token's `iss` carried
the trailing-slash spelling of the WorkOS API root, which WorkOS documents
alongside the no-slash form. The no-slash-only verifier rejected it.

These tests assert the corrected behavior at the HTTP boundary (not just the
verifier), including that identity/organization bootstrap runs normally, that the
adjacent arbitrary-path issuer still fails closed, and that nothing sensitive is
logged in either case.

Synthetic keys, tokens, and identifiers only. Nothing contacts WorkOS.
"""

from __future__ import annotations

import logging

import pytest

from app.logging_config import AUTH_LOGGER_NAME, SafeAuthFormatter
from workos_helpers import DEFAULT_ORG, DEFAULT_SID, DEFAULT_SUB, TEST_CLIENT_ID, bearer, make_token

SLASHED = "https://api.workos.com/"
SLASHLESS = "https://api.workos.com"


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


def rejections(capture: _Capture) -> list[str]:
    return [r.getMessage() for r in capture.records if "human auth rejected:" in r.getMessage()]


def rendered(capture: _Capture) -> str:
    """All records through the production formatter — what would reach Render."""
    formatter = SafeAuthFormatter("%(levelname)s [%(name)s] %(message)s")
    return "\n".join(formatter.format(r) for r in capture.records)


class TestHostedTrailingSlashIssuerNowSucceeds:
    """The precise token shape that was failing in the hosted beta."""

    def test_user_me_returns_200(self, client, workos_verifier, auth_logs):
        token = make_token(issuer=SLASHED)  # valid signature, client_id, org_id
        response = client.get("/v2/user/me", headers=bearer(token))
        assert response.status_code == 200
        assert rejections(auth_logs) == []

    def test_user_projects_returns_200(self, client, workos_verifier, linked_org, auth_logs):
        token = make_token(issuer=SLASHED)
        response = client.get("/v2/user/projects", headers=bearer(token))
        assert response.status_code == 200
        assert rejections(auth_logs) == []

    def test_no_invalid_issuer_diagnostic_is_emitted(self, client, workos_verifier, auth_logs):
        client.get("/v2/user/me", headers=bearer(make_token(issuer=SLASHED)))
        assert "auth_invalid_issuer" not in rendered(auth_logs)

    def test_identity_and_organization_bootstrap_execute_normally(
        self, client, workos_verifier, linked_org
    ):
        """The verified org_id from the trailing-slash token maps to a local org."""
        token = make_token(issuer=SLASHED, org_id=DEFAULT_ORG)
        response = client.get("/v2/user/projects", headers=bearer(token))
        assert response.status_code == 200

        me = client.get("/v2/user/me", headers=bearer(token))
        assert me.status_code == 200
        body = me.json()
        # A local identity exists and the verified organization is attached.
        assert body.get("organization") is not None

    def test_both_documented_spellings_behave_identically_over_http(
        self, client, workos_verifier
    ):
        for issuer in (SLASHLESS, SLASHED):
            response = client.get("/v2/user/me", headers=bearer(make_token(issuer=issuer)))
            assert response.status_code == 200, issuer

    def test_org_requirement_still_enforced_for_the_slash_form(
        self, client, workos_verifier, auth_logs
    ):
        """Accepting the issuer spelling must not relax the org-scoped boundary."""
        response = client.get(
            "/v2/user/projects", headers=bearer(make_token(issuer=SLASHED, org_id=None))
        )
        assert response.status_code == 403
        assert any("auth_missing_org" in line for line in rejections(auth_logs))

    def test_no_sensitive_material_is_logged_on_success(self, client, workos_verifier, auth_logs):
        token = make_token(issuer=SLASHED)
        client.get("/v2/user/me", headers=bearer(token))
        text = rendered(auth_logs)
        for secret in (
            token,
            SLASHED,
            SLASHLESS,
            "api.workos.com",
            TEST_CLIENT_ID,
            DEFAULT_SUB,
            DEFAULT_SID,
            DEFAULT_ORG,
            "eyJ",
            "Bearer ",
        ):
            assert secret not in text, f"leaked {secret!r}"


class TestArbitraryPathIssuerStillFailsClosed:
    """The adjacent value that must keep failing, with a safe diagnostic."""

    @pytest.mark.parametrize(
        "issuer",
        [
            "https://api.workos.com/arbitrary",
            f"https://api.workos.com/user_management/{TEST_CLIENT_ID}",
            "https://api.workos.com//",
            "http://api.workos.com/",
            "https://evil.api.workos.com/",
        ],
    )
    def test_returns_401_with_safe_invalid_issuer_reason(
        self, client, workos_verifier, auth_logs, issuer
    ):
        response = client.get("/v2/user/me", headers=bearer(make_token(issuer=issuer)))
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid authentication credentials"}
        lines = rejections(auth_logs)
        assert len(lines) == 1
        assert lines[0] == (
            "human auth rejected: reason=auth_invalid_issuer status=401 path=/v2/user/me"
        )

    def test_rejected_issuer_value_is_never_logged(self, client, workos_verifier, auth_logs):
        issuer = "https://api.workos.com/arbitrary-canary-path"
        token = make_token(issuer=issuer)
        client.get("/v2/user/me", headers=bearer(token))
        text = rendered(auth_logs)
        for secret in (issuer, "arbitrary-canary-path", token, "api.workos.com", "eyJ"):
            assert secret not in text, f"leaked {secret!r}"

    def test_invalid_issuer_cannot_bootstrap_an_organization(
        self, client, workos_verifier, db_session
    ):
        """A rejected token must never create local identity/organization rows."""
        from app.models_identity import Organization, User

        unseen_org = "org_01NEVERBOOTSTRAPPED000001"
        unseen_sub = "user_01NEVERBOOTSTRAPPED00001"
        before_users = db_session.query(User).count()
        before_orgs = db_session.query(Organization).count()

        response = client.get(
            "/v2/user/me",
            headers=bearer(
                make_token(
                    issuer="https://api.workos.com/arbitrary",
                    sub=unseen_sub,
                    org_id=unseen_org,
                )
            ),
        )
        assert response.status_code == 401

        db_session.expire_all()
        assert db_session.query(User).count() == before_users
        assert db_session.query(Organization).count() == before_orgs
        assert (
            db_session.query(User).filter(User.workos_user_id == unseen_sub).one_or_none()
            is None
        )
        assert (
            db_session.query(Organization)
            .filter(Organization.workos_org_id == unseen_org)
            .one_or_none()
            is None
        )

    def test_projects_route_also_logs_its_own_path(self, client, workos_verifier, auth_logs):
        client.get(
            "/v2/user/projects",
            headers=bearer(make_token(issuer="https://api.workos.com/arbitrary")),
        )
        assert rejections(auth_logs) == [
            "human auth rejected: reason=auth_invalid_issuer status=401 path=/v2/user/projects"
        ]
