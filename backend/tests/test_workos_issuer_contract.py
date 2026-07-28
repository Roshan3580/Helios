"""Checkpoint 29: the exact WorkOS issuer acceptance boundary.

WorkOS documents the AuthKit access-token issuer as the API root in BOTH standard
spellings — with and without a trailing slash. A hosted token carrying the
trailing-slash form was rejected by a verifier that accepted only the no-slash
form, producing `reason=auth_invalid_issuer status=401` on every authenticated
request despite a valid session, signature, and client_id.

The correction is a CLOSED two-entry allowlist of exact full strings, not a
normalization rule. These tests pin the boundary from both sides: the two
documented forms are accepted, and everything adjacent to them — extra paths,
doubled slashes, http, sub/superdomain lookalikes, the legacy
/user_management/<client_id> form — stays rejected.

Only synthetic RSA keys, synthetic JWKS documents, and synthetic identifiers are
used. Nothing contacts WorkOS.
"""

from __future__ import annotations

import pytest

from app.config import (
    ISSUER_MODE_DERIVED,
    ISSUER_MODE_EXPLICIT,
    WORKOS_DEFAULT_ISSUER,
    WORKOS_STANDARD_ISSUERS,
    Settings,
)
from app.security.api_keys import AuthError
from app.security.workos_auth import JWKSClient, WorkOSTokenVerifier
from workos_helpers import (
    JWKS_DOCUMENT,
    TEST_CLIENT_ID,
    make_token,
    make_token_with_wrong_key,
)

SLASHLESS = "https://api.workos.com"
SLASHED = "https://api.workos.com/"

# Values that must NEVER be accepted, in any mode, unless explicitly configured.
# Each is adjacent to a documented form, so a normalization/prefix/suffix bug
# would surface here rather than in production.
REJECTED_ISSUERS = [
    f"https://api.workos.com/user_management/{TEST_CLIENT_ID}",
    "https://api.workos.com/user_management/",
    "https://api.workos.com/foo",
    "https://api.workos.com/foo/",
    "https://api.workos.com//",
    "https://api.workos.com///",
    "https://api.workos.com/.",
    "https://api.workos.com/?x=1",
    "https://api.workos.com/#frag",
    "http://api.workos.com",
    "http://api.workos.com/",
    "https://evil.api.workos.com",
    "https://evil.api.workos.com/",
    "https://api.workos.com.evil.example",
    "https://api.workos.com.evil.example/",
    "https://apiworkos.com",
    "https://api.workos.co",
    "https://API.WORKOS.COM",
    "https://api.workos.com:443",
    " https://api.workos.com",
    "https://api.workos.com ",
    "api.workos.com",
    "",
]


def verifier(issuers) -> WorkOSTokenVerifier:
    return WorkOSTokenVerifier(
        issuers=issuers,
        client_id=TEST_CLIENT_ID,
        jwks_client=JWKSClient("https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT),
    )


def derived() -> WorkOSTokenVerifier:
    """Production derived mode: the closed two-entry standard set."""
    return verifier(WORKOS_STANDARD_ISSUERS)


# ---------------------------------------------------------------------------
# The closed set itself
# ---------------------------------------------------------------------------


class TestStandardIssuerSet:
    def test_set_has_exactly_two_entries(self):
        assert len(WORKOS_STANDARD_ISSUERS) == 2
        assert len(set(WORKOS_STANDARD_ISSUERS)) == 2

    def test_entries_are_exactly_the_two_documented_forms(self):
        assert WORKOS_STANDARD_ISSUERS == (SLASHLESS, SLASHED)

    def test_both_entries_are_https_origins_of_the_workos_api_root(self):
        for value in WORKOS_STANDARD_ISSUERS:
            assert value.startswith("https://")
            assert value.rstrip("/") == SLASHLESS

    def test_set_is_an_immutable_tuple(self):
        assert isinstance(WORKOS_STANDARD_ISSUERS, tuple)
        with pytest.raises((TypeError, AttributeError)):
            WORKOS_STANDARD_ISSUERS[0] = "https://evil.example"  # type: ignore[index]

    def test_representative_default_is_the_slashless_form(self):
        assert WORKOS_DEFAULT_ISSUER == SLASHLESS
        assert WORKOS_DEFAULT_ISSUER in WORKOS_STANDARD_ISSUERS

    def test_no_entry_is_a_bare_string_container(self):
        """A str passed to PyJWT as `issuer` would be an equality check, but a
        str used as a *container* would substring-match. Guard the type."""
        assert not isinstance(WORKOS_STANDARD_ISSUERS, str)


# ---------------------------------------------------------------------------
# Derived mode acceptance
# ---------------------------------------------------------------------------


class TestDerivedModeAcceptance:
    @pytest.mark.parametrize("issuer", [SLASHLESS, SLASHED])
    def test_both_documented_forms_are_accepted(self, issuer):
        claims = derived().verify(make_token(issuer=issuer))
        assert claims["iss"] == issuer

    @pytest.mark.parametrize("issuer", [SLASHLESS, SLASHED])
    def test_both_forms_still_require_a_valid_signature(self, issuer):
        token = make_token_with_wrong_key(issuer=issuer)
        with pytest.raises(AuthError) as exc:
            derived().verify(token)
        assert exc.value.reason == "invalid_signature"

    @pytest.mark.parametrize("issuer", [SLASHLESS, SLASHED])
    def test_both_forms_still_require_a_matching_client_id(self, issuer):
        token = make_token(issuer=issuer, client_id="client_some_other_app")
        with pytest.raises(AuthError) as exc:
            derived().verify(token)
        assert exc.value.reason == "wrong_client_id"

    @pytest.mark.parametrize("issuer", [SLASHLESS, SLASHED])
    def test_both_forms_still_require_a_present_client_id(self, issuer):
        token = make_token(issuer=issuer, client_id=None)
        with pytest.raises(AuthError) as exc:
            derived().verify(token)
        assert exc.value.reason == "missing_client_id"

    @pytest.mark.parametrize("issuer", [SLASHLESS, SLASHED])
    def test_both_forms_still_reject_an_expired_token(self, issuer):
        token = make_token(issuer=issuer, expires_in=-30)
        with pytest.raises(AuthError) as exc:
            derived().verify(token)
        assert exc.value.reason == "expired_jwt"

    @pytest.mark.parametrize("issuer", [SLASHLESS, SLASHED])
    def test_both_forms_still_require_sub_and_sid(self, issuer):
        for kwargs, reason in (({"sub": None}, "missing_claims"), ({"sid": None}, "missing_claims")):
            with pytest.raises(AuthError) as exc:
                derived().verify(make_token(issuer=issuer, **kwargs))
            assert exc.value.reason == reason


# ---------------------------------------------------------------------------
# Derived mode rejection — the boundary
# ---------------------------------------------------------------------------


class TestDerivedModeRejection:
    @pytest.mark.parametrize("issuer", REJECTED_ISSUERS)
    def test_adjacent_issuers_are_rejected(self, issuer):
        token = make_token(issuer=issuer)
        with pytest.raises(AuthError) as exc:
            derived().verify(token)
        # An absent/empty iss is a missing required claim; anything else present
        # but unlisted is a wrong issuer. Both are 401 and both map to a safe code.
        assert exc.value.reason in {"wrong_issuer", "missing_claims"}
        assert exc.value.status_code == 401

    def test_missing_iss_claim_is_rejected(self):
        """`iss` is in the required-claims list, so its absence fails closed."""
        token = make_token(issuer=None)
        with pytest.raises(AuthError) as exc:
            derived().verify(token)
        assert exc.value.reason == "missing_claims"
        assert exc.value.status_code == 401

    def test_no_rejected_issuer_is_accepted_by_substring_or_prefix(self):
        """Explicitly proves membership is exact, not prefix/suffix/substring."""
        accepted = 0
        for issuer in REJECTED_ISSUERS:
            try:
                derived().verify(make_token(issuer=issuer))
                accepted += 1
            except AuthError:
                pass
        assert accepted == 0

    def test_a_superstring_of_an_accepted_value_is_rejected(self):
        # https://api.workos.com/ is accepted; a strict superstring is not.
        with pytest.raises(AuthError):
            derived().verify(make_token(issuer=SLASHED + "extra"))


# ---------------------------------------------------------------------------
# Explicit mode
# ---------------------------------------------------------------------------


class TestExplicitMode:
    def test_explicit_slashless_root_accepts_only_slashless(self):
        v = verifier((SLASHLESS,))
        assert v.verify(make_token(issuer=SLASHLESS))["iss"] == SLASHLESS
        with pytest.raises(AuthError) as exc:
            v.verify(make_token(issuer=SLASHED))
        assert exc.value.reason == "wrong_issuer"

    def test_explicit_slashed_root_accepts_only_slashed(self):
        v = verifier((SLASHED,))
        assert v.verify(make_token(issuer=SLASHED))["iss"] == SLASHED
        with pytest.raises(AuthError) as exc:
            v.verify(make_token(issuer=SLASHLESS))
        assert exc.value.reason == "wrong_issuer"

    def test_explicit_custom_https_issuer_accepts_only_that_exact_value(self):
        custom = "https://auth.custom-domain.example"
        v = verifier((custom,))
        assert v.verify(make_token(issuer=custom))["iss"] == custom
        for other in (custom + "/", SLASHLESS, SLASHED, "https://auth.custom-domain.example:443"):
            with pytest.raises(AuthError) as exc:
                v.verify(make_token(issuer=other))
            assert exc.value.reason == "wrong_issuer"

    def test_explicit_custom_issuer_does_not_also_accept_the_standard_roots(self):
        v = verifier(("https://auth.custom-domain.example",))
        for standard in WORKOS_STANDARD_ISSUERS:
            with pytest.raises(AuthError):
                v.verify(make_token(issuer=standard))

    def test_explicit_trailing_slash_is_not_silently_normalized(self):
        """Configuring one spelling must not implicitly admit the other."""
        with_slash = verifier(("https://auth.custom-domain.example/",))
        without = verifier(("https://auth.custom-domain.example",))
        with pytest.raises(AuthError):
            with_slash.verify(make_token(issuer="https://auth.custom-domain.example"))
        with pytest.raises(AuthError):
            without.verify(make_token(issuer="https://auth.custom-domain.example/"))

    def test_explicit_mode_still_enforces_signature_and_client_id(self):
        custom = "https://auth.custom-domain.example"
        v = verifier((custom,))
        with pytest.raises(AuthError) as exc:
            v.verify(make_token_with_wrong_key(issuer=custom))
        assert exc.value.reason == "invalid_signature"
        with pytest.raises(AuthError) as exc:
            v.verify(make_token(issuer=custom, client_id="client_other"))
        assert exc.value.reason == "wrong_client_id"


# ---------------------------------------------------------------------------
# Verifier construction guards
# ---------------------------------------------------------------------------


class TestVerifierConstruction:
    def test_requires_issuers_or_issuer(self):
        with pytest.raises(ValueError):
            WorkOSTokenVerifier(
                client_id=TEST_CLIENT_ID,
                jwks_client=JWKSClient("https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT),
            )

    def test_rejects_empty_issuer_collection(self):
        with pytest.raises(ValueError):
            verifier(())

    def test_rejects_empty_string_entries(self):
        with pytest.raises(ValueError):
            verifier(("https://api.workos.com", ""))

    def test_single_issuer_kwarg_becomes_an_exact_one_entry_set(self):
        v = WorkOSTokenVerifier(
            issuer=SLASHLESS,
            client_id=TEST_CLIENT_ID,
            jwks_client=JWKSClient("https://jwks.test/keys", fetcher=lambda: JWKS_DOCUMENT),
        )
        assert v.accepted_issuers == (SLASHLESS,)

    def test_accepted_issuers_is_stored_as_a_tuple_not_a_string(self):
        """A str would make PyJWT's `in` a substring test if it ever took the
        container branch. Stored type must be a tuple."""
        assert isinstance(derived().accepted_issuers, tuple)
        assert derived().accepted_issuers == WORKOS_STANDARD_ISSUERS


# ---------------------------------------------------------------------------
# Settings-level mode resolution
# ---------------------------------------------------------------------------


class TestSettingsModes:
    def test_unset_issuer_derives_the_standard_set(self):
        s = Settings(workos_client_id="client_synthetic_1", workos_issuer="")
        assert s.workos_issuer_mode == ISSUER_MODE_DERIVED
        assert s.workos_accepted_issuers == WORKOS_STANDARD_ISSUERS

    @pytest.mark.parametrize(
        "explicit",
        [SLASHLESS, SLASHED, "https://auth.custom-domain.example"],
    )
    def test_explicit_issuer_yields_exactly_one_value_verbatim(self, explicit):
        s = Settings(workos_client_id="client_synthetic_1", workos_issuer=explicit)
        assert s.workos_issuer_mode == ISSUER_MODE_EXPLICIT
        assert s.workos_accepted_issuers == (explicit,)

    def test_unconfigured_deployment_accepts_nothing(self):
        s = Settings(workos_client_id="", workos_issuer="")
        assert s.workos_accepted_issuers == ()

    def test_jwks_derivation_is_unchanged_and_client_specific(self):
        s = Settings(workos_client_id="client_synthetic_1", workos_issuer="")
        assert s.workos_jwks_url_resolved == (
            "https://api.workos.com/sso/jwks/client_synthetic_1"
        )

    def test_explicit_issuer_does_not_change_jwks_derivation(self):
        s = Settings(
            workos_client_id="client_synthetic_1",
            workos_issuer="https://auth.custom-domain.example",
        )
        assert s.workos_jwks_url_resolved == (
            "https://api.workos.com/sso/jwks/client_synthetic_1"
        )
