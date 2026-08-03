"""Hosted issuer regressions reproduced end-to-end through authenticated routes.

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

from app.config import workos_multi_application_issuer
from app.logging_config import AUTH_LOGGER_NAME, SafeAuthFormatter
from app.security.workos_auth import JWKSClient, WorkOSTokenVerifier, set_verifier_for_tests
from workos_helpers import DEFAULT_ORG, DEFAULT_SID, DEFAULT_SUB, TEST_CLIENT_ID, bearer, make_token
from workos_helpers import JWKS_DOCUMENT

SLASHED = "https://api.workos.com/"
SLASHLESS = "https://api.workos.com"
ISSUER_CLIENT_ID = "client_default_issuer_app_0001"
OTHER_CLIENT_ID = "client_untrusted_app_0001"
MULTI_ISSUER = workos_multi_application_issuer(ISSUER_CLIENT_ID)


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


@pytest.fixture()
def multi_app_verifier():
    """Production multi-app shape: current app A, configured issuer app B."""
    verifier = WorkOSTokenVerifier(
        issuers=(MULTI_ISSUER,),
        client_id=TEST_CLIENT_ID,
        jwks_client=JWKSClient("https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT),
    )
    set_verifier_for_tests(verifier)
    try:
        yield verifier
    finally:
        set_verifier_for_tests(None)


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


class TestConfirmedMultiApplicationHostedShape:
    def test_user_me_and_projects_return_200_and_bootstrap(
        self, client, multi_app_verifier, db_session, auth_logs
    ):
        from app.models_identity import Organization, User

        assert db_session.query(User).count() == 0
        assert db_session.query(Organization).count() == 0
        token = make_token(
            issuer=MULTI_ISSUER,
            client_id=TEST_CLIENT_ID,
            org_id=DEFAULT_ORG,
        )
        me = client.get("/v2/user/me", headers=bearer(token))
        projects = client.get("/v2/user/projects", headers=bearer(token))
        assert me.status_code == 200
        assert projects.status_code == 200
        assert me.json().get("organization") is not None
        assert rejections(auth_logs) == []
        db_session.expire_all()
        assert db_session.query(User).count() == 1
        assert db_session.query(Organization).count() == 1

    @pytest.mark.parametrize(
        ("issuer", "client_id", "reason"),
        [
            (
                workos_multi_application_issuer(OTHER_CLIENT_ID),
                TEST_CLIENT_ID,
                "auth_invalid_issuer",
            ),
            (MULTI_ISSUER, ISSUER_CLIENT_ID, "auth_invalid_client_id"),
            (SLASHLESS, TEST_CLIENT_ID, "auth_invalid_issuer"),
            (MULTI_ISSUER + "/", TEST_CLIENT_ID, "auth_invalid_issuer"),
        ],
    )
    def test_negative_shapes_fail_without_bootstrap(
        self,
        client,
        multi_app_verifier,
        db_session,
        auth_logs,
        issuer,
        client_id,
        reason,
    ):
        from app.models_identity import Organization, User

        before_users = db_session.query(User).count()
        before_orgs = db_session.query(Organization).count()
        token = make_token(
            issuer=issuer,
            client_id=client_id,
            sub="user_01MULTIAPPNEVERBOOTSTRAP01",
            org_id="org_01MULTIAPPNEVERBOOTSTRAP001",
        )
        response = client.get("/v2/user/projects", headers=bearer(token))
        assert response.status_code == 401
        assert response.json() == {"detail": "invalid authentication credentials"}
        assert rejections(auth_logs) == [
            f"human auth rejected: reason={reason} status=401 path=/v2/user/projects"
        ]
        db_session.expire_all()
        assert db_session.query(User).count() == before_users
        assert db_session.query(Organization).count() == before_orgs

    def test_missing_org_remains_safe_403(self, client, multi_app_verifier, auth_logs):
        response = client.get(
            "/v2/user/projects",
            headers=bearer(make_token(issuer=MULTI_ISSUER, org_id=None)),
        )
        assert response.status_code == 403
        assert rejections(auth_logs) == [
            "human auth rejected: reason=auth_missing_org status=403 path=/v2/user/projects"
        ]

    def test_no_multi_app_identifier_or_token_is_logged(
        self, client, multi_app_verifier, auth_logs
    ):
        token = make_token(issuer=MULTI_ISSUER)
        assert client.get("/v2/user/me", headers=bearer(token)).status_code == 200
        text = rendered(auth_logs)
        for value in (
            token,
            MULTI_ISSUER,
            TEST_CLIENT_ID,
            ISSUER_CLIENT_ID,
            DEFAULT_SUB,
            DEFAULT_SID,
            DEFAULT_ORG,
            "Bearer ",
            "eyJ",
        ):
            assert value not in text


class TestArbitraryPathIssuerStillFailsClosed:
    """Adjacent values that must keep failing, with a safe diagnostic."""

    @pytest.mark.parametrize(
        "issuer",
        [
            "https://api.workos.com/arbitrary",
            "https://api.workos.com/user_management/client_some_other_app",
            "https://api.workos.com/user_management/",
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
