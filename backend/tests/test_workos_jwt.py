"""WorkOS JWT verification and JWKS-cache behavior (no WorkOS network access)."""

import logging

import pytest

from app.security.api_keys import AuthError
from app.security.workos_auth import JWKSClient, WorkOSTokenVerifier

from workos_helpers import (
    JWKS_DOCUMENT,
    JWKS_DOCUMENT_ROTATED,
    TEST_CLIENT_ID,
    TEST_ISSUER,
    make_token,
    make_token_with_rotated_key,
    make_token_with_wrong_key,
)


def make_verifier(fetcher=None, **jwks_kwargs) -> WorkOSTokenVerifier:
    client = JWKSClient(
        "https://jwks.test/keys", fetcher=fetcher or (lambda: JWKS_DOCUMENT), **jwks_kwargs
    )
    return WorkOSTokenVerifier(
        issuer=TEST_ISSUER, client_id=TEST_CLIENT_ID, jwks_client=client
    )


class TestVerification:
    def test_valid_token_returns_claims(self):
        claims = make_verifier().verify(make_token())
        assert claims["sub"].startswith("user_")
        assert claims["sid"].startswith("session_")
        assert claims["org_id"].startswith("org_")
        assert claims["client_id"] == TEST_CLIENT_ID
        assert claims["role"] == "member"

    def test_official_issuer_is_api_root(self):
        # The AuthKit access-token issuer is the API root, not a
        # /user_management/<client_id> path.
        assert TEST_ISSUER == "https://api.workos.com"
        claims = make_verifier().verify(make_token(issuer=TEST_ISSUER))
        assert claims["iss"] == "https://api.workos.com"

    def test_user_management_issuer_rejected(self):
        # A token whose issuer is the old (incorrect) /user_management/ form
        # must be rejected: it is not what AuthKit emits.
        token = make_token(
            issuer=f"https://api.workos.com/user_management/{TEST_CLIENT_ID}"
        )
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "wrong_issuer"

    def test_trailing_slash_issuer_rejected(self):
        # Issuer comparison is exact: a trailing slash does not match the
        # canonical https://api.workos.com.
        token = make_token(issuer="https://api.workos.com/")
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "wrong_issuer"

    def test_correct_client_id_accepted(self):
        claims = make_verifier().verify(make_token(client_id=TEST_CLIENT_ID))
        assert claims["client_id"] == TEST_CLIENT_ID

    def test_wrong_client_id_rejected(self):
        # A token correctly signed by WorkOS but for a DIFFERENT application
        # (different client_id) must be rejected — application isolation.
        token = make_token(client_id="client_some_other_app")
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "wrong_client_id"

    def test_missing_client_id_rejected(self):
        token = make_token(client_id=None)
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "missing_client_id"

    def test_malformed_token_rejected(self):
        with pytest.raises(AuthError) as exc:
            make_verifier().verify("not.a.jwt")
        assert exc.value.status_code == 401

    def test_wrong_signature_rejected(self):
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(make_token_with_wrong_key())
        assert exc.value.reason == "invalid_signature"

    def test_unsupported_algorithm_rejected(self):
        token = make_token(algorithm="HS256")
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "unsupported_algorithm"

    def test_expired_token_rejected(self):
        token = make_token(expires_in=-60)
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "expired_jwt"

    def test_wrong_issuer_rejected(self):
        token = make_token(issuer="https://evil.example/issuer")
        with pytest.raises(AuthError) as exc:
            make_verifier().verify(token)
        assert exc.value.reason == "wrong_issuer"

    def test_missing_sub_rejected(self):
        token = make_token(sub=None)
        with pytest.raises(AuthError):
            make_verifier().verify(token)

    def test_missing_sid_rejected(self):
        token = make_token(sid=None)
        with pytest.raises(AuthError):
            make_verifier().verify(token)


class TestJWKSCache:
    def test_cache_reused_between_verifications(self):
        calls = {"count": 0}

        def counting_fetcher():
            calls["count"] += 1
            return JWKS_DOCUMENT

        verifier = make_verifier(fetcher=counting_fetcher)
        verifier.verify(make_token())
        verifier.verify(make_token())
        verifier.verify(make_token())
        assert calls["count"] == 1  # one fetch, cached afterwards

    def test_unknown_kid_triggers_exactly_one_refresh(self):
        documents = [JWKS_DOCUMENT, JWKS_DOCUMENT_ROTATED]
        calls = {"count": 0}

        def rotating_fetcher():
            calls["count"] += 1
            return documents[min(calls["count"] - 1, 1)]

        verifier = make_verifier(fetcher=rotating_fetcher)
        verifier.verify(make_token())  # fetch 1: old document
        # Token signed by the rotated key: unknown kid -> one refresh -> valid.
        claims = verifier.verify(make_token_with_rotated_key())
        assert claims["sub"]
        assert calls["count"] == 2

    def test_still_unknown_kid_after_refresh_fails_closed(self):
        verifier = make_verifier()  # never serves the rotated kid
        with pytest.raises(AuthError) as exc:
            verifier.verify(make_token_with_rotated_key())
        assert exc.value.reason == "unknown_signing_key"

    def test_jwks_fetch_failure_fails_closed(self):
        def broken_fetcher():
            raise TimeoutError("jwks fetch timed out")

        verifier = make_verifier(fetcher=broken_fetcher)
        with pytest.raises(AuthError) as exc:
            verifier.verify(make_token())
        assert exc.value.reason == "jwks_unavailable"
        assert exc.value.status_code == 401

    def test_cache_expiry_refetches(self):
        calls = {"count": 0}

        def counting_fetcher():
            calls["count"] += 1
            return JWKS_DOCUMENT

        verifier = make_verifier(fetcher=counting_fetcher, cache_ttl=0)
        verifier.verify(make_token())
        verifier.verify(make_token())
        assert calls["count"] >= 2  # ttl 0 -> refresh each time


class TestNoLeakage:
    def test_jwt_absent_from_logs_and_errors(self, caplog):
        token = make_token(expires_in=-60)
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(AuthError) as exc:
                make_verifier().verify(token)
        combined = "\n".join(r.getMessage() for r in caplog.records)
        assert token not in combined
        assert token not in str(exc.value)
