"""Checkpoint 30: strict WorkOS multi-application issuer modes.

Only synthetic keys, tokens, and identifiers are used. Nothing contacts WorkOS.
"""

from __future__ import annotations

import pytest

from app.config import (
    ISSUER_MODE_DERIVED,
    ISSUER_MODE_EXPLICIT,
    ISSUER_MODE_MULTI_APPLICATION,
    WORKOS_STANDARD_ISSUERS,
    Settings,
    workos_multi_application_issuer,
)
from app.security.api_keys import AuthError
from app.security.workos_auth import JWKSClient, WorkOSTokenVerifier
from workos_helpers import JWKS_DOCUMENT, TEST_CLIENT_ID, make_token, make_token_with_wrong_key

STANDARD_NO_SLASH = "https://api.workos.com"
STANDARD_SLASH = "https://api.workos.com/"
ISSUER_CLIENT_ID = "client_default_app_0001"
OTHER_CLIENT_ID = "client_other_app_0001"
MULTI_ISSUER = f"https://api.workos.com/user_management/{ISSUER_CLIENT_ID}"


def verifier(issuers: tuple[str, ...]) -> WorkOSTokenVerifier:
    return WorkOSTokenVerifier(
        issuers=issuers,
        client_id=TEST_CLIENT_ID,
        jwks_client=JWKSClient("https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT),
    )


def standard_verifier() -> WorkOSTokenVerifier:
    return verifier(WORKOS_STANDARD_ISSUERS)


def multi_verifier() -> WorkOSTokenVerifier:
    return verifier((workos_multi_application_issuer(ISSUER_CLIENT_ID),))


class TestIssuerModes:
    def test_standard_mode_retains_exactly_two_roots(self):
        settings = Settings(workos_client_id=TEST_CLIENT_ID)
        assert settings.workos_issuer_mode == ISSUER_MODE_DERIVED
        assert settings.workos_accepted_issuers == (
            STANDARD_NO_SLASH,
            STANDARD_SLASH,
        )

    def test_multi_application_mode_derives_exactly_one_no_slash_issuer(self):
        settings = Settings(
            workos_client_id=TEST_CLIENT_ID,
            workos_issuer_client_id=ISSUER_CLIENT_ID,
        )
        assert settings.workos_issuer_mode == ISSUER_MODE_MULTI_APPLICATION
        assert settings.workos_accepted_issuers == (MULTI_ISSUER,)
        assert not settings.workos_accepted_issuers[0].endswith("/")

    def test_explicit_mode_accepts_exactly_the_configured_value(self):
        explicit = "https://auth.synthetic.example/exact/"
        settings = Settings(workos_client_id=TEST_CLIENT_ID, workos_issuer=explicit)
        assert settings.workos_issuer_mode == ISSUER_MODE_EXPLICIT
        assert settings.workos_accepted_issuers == (explicit,)

    def test_ambiguous_mode_accepts_nothing_and_reports_safe_issue(self):
        settings = Settings(
            helios_environment="staging",
            database_url="postgresql://synthetic@db.example/helios_staging",
            cors_origins="https://helios.example",
            workos_client_id=TEST_CLIENT_ID,
            workos_issuer_client_id=ISSUER_CLIENT_ID,
            workos_issuer="https://auth.synthetic.example",
        )
        assert settings.workos_accepted_issuers == ()
        assert {issue.code for issue in settings.deployment_issues()} >= {
            "issuer_configuration_ambiguous"
        }

    def test_current_and_issuer_application_identities_remain_separate(self):
        settings = Settings(
            workos_client_id=TEST_CLIENT_ID,
            workos_issuer_client_id=ISSUER_CLIENT_ID,
        )
        assert TEST_CLIENT_ID not in settings.workos_accepted_issuers[0]
        assert ISSUER_CLIENT_ID in settings.workos_accepted_issuers[0]
        assert settings.workos_jwks_url_resolved.endswith(f"/{TEST_CLIENT_ID}")
        assert ISSUER_CLIENT_ID not in settings.workos_jwks_url_resolved

    def test_current_and_issuer_client_ids_may_be_equal(self):
        settings = Settings(
            workos_client_id=TEST_CLIENT_ID,
            workos_issuer_client_id=TEST_CLIENT_ID,
        )
        assert settings.workos_accepted_issuers == (
            f"https://api.workos.com/user_management/{TEST_CLIENT_ID}",
        )

    def test_mode_is_not_selected_from_token_data(self):
        settings = Settings(workos_client_id=TEST_CLIENT_ID)
        token = make_token(issuer=MULTI_ISSUER)
        with pytest.raises(AuthError):
            verifier(settings.workos_accepted_issuers).verify(token)
        assert settings.workos_issuer_mode == ISSUER_MODE_DERIVED
        assert settings.workos_accepted_issuers == WORKOS_STANDARD_ISSUERS


class TestStandardMode:
    @pytest.mark.parametrize("issuer", WORKOS_STANDARD_ISSUERS)
    def test_accepts_each_standard_root(self, issuer):
        assert standard_verifier().verify(make_token(issuer=issuer))["iss"] == issuer

    @pytest.mark.parametrize(
        "issuer",
        [MULTI_ISSUER, MULTI_ISSUER + "/", "https://api.workos.com/path"],
    )
    def test_rejects_non_standard_issuers(self, issuer):
        with pytest.raises(AuthError) as exc:
            standard_verifier().verify(make_token(issuer=issuer))
        assert exc.value.reason == "wrong_issuer"

    def test_still_requires_valid_signature(self):
        with pytest.raises(AuthError) as exc:
            standard_verifier().verify(make_token_with_wrong_key())
        assert exc.value.reason == "invalid_signature"

    def test_still_requires_current_client_id(self):
        with pytest.raises(AuthError) as exc:
            standard_verifier().verify(make_token(client_id=OTHER_CLIENT_ID))
        assert exc.value.reason == "wrong_client_id"

    def test_still_requires_present_client_id(self):
        with pytest.raises(AuthError) as exc:
            standard_verifier().verify(make_token(client_id=None))
        assert exc.value.reason == "missing_client_id"

    def test_still_rejects_expired_token(self):
        with pytest.raises(AuthError) as exc:
            standard_verifier().verify(make_token(expires_in=-30))
        assert exc.value.reason == "expired_jwt"

    @pytest.mark.parametrize("claim", ["sub", "sid"])
    def test_still_requires_identity_claims(self, claim):
        with pytest.raises(AuthError) as exc:
            standard_verifier().verify(make_token(**{claim: None}))
        assert exc.value.reason == "missing_claims"


class TestMultiApplicationMode:
    def test_accepts_confirmed_shape(self):
        claims = multi_verifier().verify(
            make_token(issuer=MULTI_ISSUER, client_id=TEST_CLIENT_ID)
        )
        assert claims["iss"] == MULTI_ISSUER
        assert claims["client_id"] == TEST_CLIENT_ID

    @pytest.mark.parametrize(
        "issuer",
        [
            f"https://api.workos.com/user_management/{TEST_CLIENT_ID}",
            f"https://api.workos.com/user_management/{OTHER_CLIENT_ID}",
            MULTI_ISSUER + "/",
            STANDARD_NO_SLASH,
            STANDARD_SLASH,
            "https://api.workos.com/user_management/arbitrary",
            MULTI_ISSUER + "/extra",
        ],
    )
    def test_rejects_every_adjacent_issuer(self, issuer):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token(issuer=issuer))
        assert exc.value.reason == "wrong_issuer"
        assert exc.value.status_code == 401

    @pytest.mark.parametrize("client_id", [ISSUER_CLIENT_ID, OTHER_CLIENT_ID])
    def test_rejects_client_id_that_is_not_current_application(self, client_id):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token(issuer=MULTI_ISSUER, client_id=client_id))
        assert exc.value.reason == "wrong_client_id"

    def test_rejects_missing_client_id(self):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token(issuer=MULTI_ISSUER, client_id=None))
        assert exc.value.reason == "missing_client_id"

    def test_rejects_missing_issuer(self):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token(issuer=None))
        assert exc.value.reason == "missing_claims"

    def test_rejects_wrong_signing_key(self):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token_with_wrong_key(issuer=MULTI_ISSUER))
        assert exc.value.reason == "invalid_signature"

    def test_rejects_expired_token(self):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token(issuer=MULTI_ISSUER, expires_in=-30))
        assert exc.value.reason == "expired_jwt"

    @pytest.mark.parametrize("claim", ["sub", "sid"])
    def test_rejects_missing_required_identity_claims(self, claim):
        with pytest.raises(AuthError) as exc:
            multi_verifier().verify(make_token(issuer=MULTI_ISSUER, **{claim: None}))
        assert exc.value.reason == "missing_claims"

    def test_accepted_collection_is_exactly_one_immutable_tuple(self):
        accepted = multi_verifier().accepted_issuers
        assert isinstance(accepted, tuple)
        assert accepted == (MULTI_ISSUER,)

    def test_rejected_issuer_is_not_matched_by_prefix_suffix_or_substring(self):
        for issuer in (
            "prefix" + MULTI_ISSUER,
            MULTI_ISSUER + "suffix",
            MULTI_ISSUER + "/nested",
            MULTI_ISSUER.upper(),
        ):
            with pytest.raises(AuthError) as exc:
                multi_verifier().verify(make_token(issuer=issuer))
            assert exc.value.reason == "wrong_issuer"


class TestExplicitMode:
    def test_explicit_issuer_is_byte_exact(self):
        explicit = "https://auth.synthetic.example/exact"
        exact = verifier((explicit,))
        assert exact.verify(make_token(issuer=explicit))["iss"] == explicit
        for other in (explicit + "/", STANDARD_NO_SLASH, MULTI_ISSUER):
            with pytest.raises(AuthError) as exc:
                exact.verify(make_token(issuer=other))
            assert exc.value.reason == "wrong_issuer"

    def test_explicit_slashless_root_does_not_accept_slashed_root(self):
        exact = verifier((STANDARD_NO_SLASH,))
        assert exact.verify(make_token(issuer=STANDARD_NO_SLASH))["iss"] == STANDARD_NO_SLASH
        with pytest.raises(AuthError):
            exact.verify(make_token(issuer=STANDARD_SLASH))

    def test_explicit_slashed_root_does_not_accept_slashless_root(self):
        exact = verifier((STANDARD_SLASH,))
        assert exact.verify(make_token(issuer=STANDARD_SLASH))["iss"] == STANDARD_SLASH
        with pytest.raises(AuthError):
            exact.verify(make_token(issuer=STANDARD_NO_SLASH))

    def test_explicit_multi_app_does_not_add_a_slash_variant(self):
        exact = verifier((MULTI_ISSUER,))
        assert exact.verify(make_token(issuer=MULTI_ISSUER))["iss"] == MULTI_ISSUER
        with pytest.raises(AuthError):
            exact.verify(make_token(issuer=MULTI_ISSUER + "/"))

    def test_explicit_custom_slash_is_not_normalized(self):
        with_slash = verifier(("https://auth.synthetic.example/",))
        without_slash = verifier(("https://auth.synthetic.example",))
        with pytest.raises(AuthError):
            with_slash.verify(make_token(issuer="https://auth.synthetic.example"))
        with pytest.raises(AuthError):
            without_slash.verify(make_token(issuer="https://auth.synthetic.example/"))

    def test_explicit_custom_does_not_add_standard_roots(self):
        exact = verifier(("https://auth.synthetic.example",))
        for issuer in WORKOS_STANDARD_ISSUERS:
            with pytest.raises(AuthError):
                exact.verify(make_token(issuer=issuer))

    def test_explicit_mode_still_enforces_signature(self):
        explicit = "https://auth.synthetic.example"
        with pytest.raises(AuthError) as exc:
            verifier((explicit,)).verify(make_token_with_wrong_key(issuer=explicit))
        assert exc.value.reason == "invalid_signature"

    def test_explicit_mode_still_enforces_current_client_id(self):
        explicit = "https://auth.synthetic.example"
        with pytest.raises(AuthError) as exc:
            verifier((explicit,)).verify(
                make_token(issuer=explicit, client_id=OTHER_CLIENT_ID)
            )
        assert exc.value.reason == "wrong_client_id"


class TestVerifierConstruction:
    def test_requires_issuers_or_issuer(self):
        with pytest.raises(ValueError):
            WorkOSTokenVerifier(
                client_id=TEST_CLIENT_ID,
                jwks_client=JWKSClient(
                    "https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT
                ),
            )

    def test_requires_a_nonempty_issuer_collection(self):
        with pytest.raises(ValueError):
            verifier(())
        with pytest.raises(ValueError):
            verifier((STANDARD_NO_SLASH, ""))

    def test_stores_issuers_as_an_immutable_tuple(self):
        accepted = standard_verifier().accepted_issuers
        assert isinstance(accepted, tuple)
        assert accepted == WORKOS_STANDARD_ISSUERS

    def test_single_issuer_keyword_becomes_one_entry_tuple(self):
        exact = WorkOSTokenVerifier(
            issuer=MULTI_ISSUER,
            client_id=TEST_CLIENT_ID,
            jwks_client=JWKSClient(
                "https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT
            ),
        )
        assert exact.accepted_issuers == (MULTI_ISSUER,)


class TestAdditionalSettingsGuards:
    def test_unconfigured_settings_accept_nothing(self):
        assert Settings(workos_client_id="").workos_accepted_issuers == ()

    def test_multi_application_resolved_issuer_matches_accepted_value(self):
        settings = Settings(
            workos_client_id=TEST_CLIENT_ID,
            workos_issuer_client_id=ISSUER_CLIENT_ID,
        )
        assert settings.workos_issuer_resolved == MULTI_ISSUER
        assert settings.workos_accepted_issuers == (settings.workos_issuer_resolved,)

    def test_explicit_issuer_does_not_change_jwks_derivation(self):
        settings = Settings(
            workos_client_id=TEST_CLIENT_ID,
            workos_issuer="https://auth.synthetic.example",
        )
        assert settings.workos_jwks_url_resolved == (
            f"https://api.workos.com/sso/jwks/{TEST_CLIENT_ID}"
        )

    def test_explicit_jwks_override_is_used_verbatim(self):
        override = f"https://api.workos.com/sso/jwks/{TEST_CLIENT_ID}"
        settings = Settings(workos_client_id=TEST_CLIENT_ID, workos_jwks_url=override)
        assert settings.workos_jwks_url_resolved == override
