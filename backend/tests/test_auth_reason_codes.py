"""Checkpoint 25: safe structured auth reason codes (no token/secret leakage).

The human-auth boundary must emit a bounded, credential-free reason code for
each rejection so a hosted "signed in but 401 on every API call" failure can be
attributed to a concrete cause — without ever logging the JWT, Authorization
header, cookie, email, or any secret. The client response stays generic.

Logs are captured with a directly-attached handler (independent of pytest's
logging plugin).
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

import pytest

from workos_helpers import bearer, make_token, make_token_with_wrong_key

_LOGGER = "helios.auth.human"


@contextmanager
def capture_auth_logs():
    logger = logging.getLogger(_LOGGER)

    class _ListHandler(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.INFO)
            self.records: list[logging.LogRecord] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.records.append(record)

    handler = _ListHandler()
    prev_level = logger.level
    # Alembic's fileConfig (run by the migration fixture) uses
    # disable_existing_loggers=True, which sets `.disabled = True` on the app's
    # loggers in-process — a test-only artifact (in production, migrations run
    # as a separate pre-deploy process). Re-enable for the duration so this test
    # observes the real production logging path.
    prev_disabled = logger.disabled
    prev_global_disable = logging.root.manager.disable
    logging.disable(logging.NOTSET)
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        yield handler.records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)
        logger.disabled = prev_disabled
        logging.disable(prev_global_disable)


def _reason_codes(records) -> list[str]:
    codes = []
    for record in records:
        msg = record.getMessage()
        if "human auth rejected: reason=" in msg:
            codes.append(msg.split("reason=", 1)[1].split(" ", 1)[0])
    return codes


def _all_log_text(records) -> str:
    return "\n".join(record.getMessage() for record in records)


class TestAuthReasonCodes:
    def test_expired_token_emits_expired_reason(self, client, workos_verifier):
        token = make_token(expires_in=-30)
        with capture_auth_logs() as records:
            response = client.get("/v2/user/me", headers=bearer(token))
        assert response.status_code == 401
        assert "auth_expired_token" in _reason_codes(records)
        assert token not in _all_log_text(records)

    def test_wrong_signature_emits_invalid_signature_reason(self, client, workos_verifier):
        token = make_token_with_wrong_key()
        with capture_auth_logs() as records:
            response = client.get("/v2/user/me", headers=bearer(token))
        assert response.status_code == 401
        assert "auth_invalid_signature" in _reason_codes(records)
        assert token not in _all_log_text(records)

    def test_missing_token_emits_missing_reason(self, client, workos_verifier):
        with capture_auth_logs() as records:
            response = client.get("/v2/user/me")
        assert response.status_code == 401
        assert "auth_missing_token" in _reason_codes(records)

    def test_missing_org_on_org_route_emits_missing_org_reason(self, client, workos_verifier):
        token = make_token(org_id=None)
        with capture_auth_logs() as records:
            response = client.get("/v2/user/projects", headers=bearer(token))
        assert response.status_code == 403
        assert "auth_missing_org" in _reason_codes(records)
        assert token not in _all_log_text(records)

    def test_generic_response_detail_reveals_no_internals(self, client, workos_verifier):
        # Client-facing 401 detail is generic; no reason code / issuer / JWKS.
        body = client.get(
            "/v2/user/me", headers=bearer(make_token_with_wrong_key())
        ).json()
        assert body["detail"] == "invalid authentication credentials"
        for leaked in ("issuer", "jwks", "signature", "kid", "auth_"):
            assert leaked not in body["detail"]

    @pytest.mark.parametrize("org_id", [None, "org_01VALIDORG0000000000001"])
    def test_reason_codes_never_include_token_material(self, client, workos_verifier, org_id):
        token = make_token(org_id=org_id, expires_in=-5)
        with capture_auth_logs() as records:
            client.get("/v2/user/me", headers=bearer(token))
        assert token not in _all_log_text(records)
