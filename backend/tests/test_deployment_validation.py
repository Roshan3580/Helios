"""Deployment contract validation unit tests."""

from __future__ import annotations

from app.deployment_validation import sanitize_message, validate_settings

# Official WorkOS AuthKit contract used across staging/production tests:
#   issuer = https://api.workos.com  (API root, no path)
#   jwks   = https://api.workos.com/sso/jwks/<client_id>
_CLIENT_ID = "client_staging_example"
_ISSUER = "https://api.workos.com"
_JWKS = f"https://api.workos.com/sso/jwks/{_CLIENT_ID}"


def _staging(**overrides):
    """Valid staging settings with overridable fields."""
    base = dict(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios_staging",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_client_id=_CLIENT_ID,
        workos_issuer=_ISSUER,
        workos_jwks_url=_JWKS,
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    base.update(overrides)
    return validate_settings(**base)


def _local(**overrides):
    base = dict(
        environment="local",
        database_url="postgresql://helios:helios@localhost:5433/helios",
        cors_origins=["http://localhost:5173"],
        workos_client_id="",
        workos_issuer="http://127.0.0.1:9/",
        workos_jwks_url="http://127.0.0.1:9/jwks",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    base.update(overrides)
    return validate_settings(**base)


def test_local_allows_loopback_defaults():
    assert _local() == []


def test_staging_rejects_e2e_and_loopback():
    codes = {
        i.code
        for i in _staging(
            workos_issuer="http://127.0.0.1:9/",
            workos_jwks_url="http://127.0.0.1:9/jwks",
            helios_e2e_test_mode=True,
        )
    }
    assert "e2e_forbidden" in codes
    assert "issuer_loopback" in codes or "issuer_https" in codes
    assert "jwks_loopback" in codes or "jwks_https" in codes


def test_staging_rejects_wildcard_and_test_db():
    codes = {
        i.code
        for i in _staging(
            database_url="postgresql://u:p@localhost:5434/helios_test",
            cors_origins=["*"],
        )
    }
    assert "cors_wildcard" in codes
    assert "database_is_test" in codes


def test_staging_requires_https_cors_and_workos():
    assert _staging(database_url="postgresql://u:p@db.example/helios") == []


def test_openai_required_only_when_narrative_enabled():
    assert _staging(analyst_provider="openai") == []

    bad = _staging(
        narrative_enabled=True,
        allow_third_party=True,
        analyst_provider="openai",
    )
    assert any(i.code == "openai_key_required" for i in bad)


def test_sanitize_message_redacts_prefixes():
    msg = sanitize_message("bad postgresql://user:pass@host/db and sk_live_xxx")
    assert "postgresql://" not in msg
    assert "sk_live" not in msg
    assert "[redacted]" in msg


def test_staging_rejects_demo_mode():
    assert any(i.code == "demo_mode_forbidden" for i in _staging(helios_demo_mode=True))


def test_production_rejects_demo_mode():
    issues = _staging(
        environment="production",
        cors_origins=["https://helios.example.com"],
        helios_demo_mode=True,
    )
    assert any(i.code == "demo_mode_forbidden" for i in issues)


def test_staging_allows_demo_mode_false():
    assert _staging() == []


def test_production_allows_demo_mode_false():
    assert _staging(environment="production", cors_origins=["https://helios.example.com"]) == []


def test_local_allows_demo_mode_true():
    assert _local(helios_demo_mode=True) == []


def test_unknown_environment_prod_is_fatal():
    """Unknown environment 'prod' must fail closed (H1)."""
    issues = _staging(environment="prod")
    assert any(i.code == "unknown_environment" for i in issues)


def test_unknown_environment_with_demo_mode_fails_closed():
    """Unknown environment must fail closed even when combined with demo_mode (H1)."""
    issues = _staging(
        environment="live",
        cors_origins=["https://example.com"],
        helios_demo_mode=True,
    )
    assert any(i.code == "unknown_environment" for i in issues)
    assert any(i.code == "demo_mode_forbidden" for i in issues)


def test_unknown_environment_production_variant_fails():
    """Arbitrary unknown environment like 'production-1' must fail closed."""
    issues = _staging(environment="production-1", cors_origins=["https://example.com"])
    assert any(i.code == "unknown_environment" for i in issues)


# ---------------------------------------------------------------------------
# WorkOS AuthKit verifier contract (Checkpoint 26).
# ---------------------------------------------------------------------------


def test_staging_accepts_official_workos_contract():
    # Canonical issuer (API root, no path) + application-specific JWKS.
    assert _staging() == []


def test_staging_rejects_user_management_issuer():
    # The old /user_management/<client_id> issuer is NOT the access-token
    # issuer and must be rejected as a misconfiguration.
    codes = {
        i.code
        for i in _staging(
            workos_issuer=f"https://api.workos.com/user_management/{_CLIENT_ID}"
        )
    }
    assert "issuer_contract" in codes


def test_staging_rejects_arbitrary_workos_issuer_path():
    codes = {i.code for i in _staging(workos_issuer="https://api.workos.com/anything")}
    assert "issuer_contract" in codes


def test_staging_rejects_issuer_with_query_or_fragment():
    codes = {i.code for i in _staging(workos_issuer="https://api.workos.com?x=1")}
    assert "issuer_contract" in codes


def test_staging_accepts_explicit_custom_https_issuer():
    # A legitimate custom WorkOS auth domain (non-workos host) is allowed as an
    # explicit HTTPS issuer; JWKS is still served from api.workos.com.
    assert _staging(workos_issuer="https://auth.example.com") == []


def test_staging_rejects_http_issuer():
    codes = {i.code for i in _staging(workos_issuer="http://api.workos.com")}
    assert "issuer_https" in codes


def test_staging_rejects_non_workos_jwks_host():
    codes = {
        i.code
        for i in _staging(workos_jwks_url=f"https://cdn.example.com/sso/jwks/{_CLIENT_ID}")
    }
    assert "jwks_contract" in codes


def test_staging_rejects_wrong_jwks_path():
    codes = {
        i.code for i in _staging(workos_jwks_url=f"https://api.workos.com/keys/{_CLIENT_ID}")
    }
    assert "jwks_contract" in codes


def test_staging_rejects_jwks_client_id_mismatch():
    codes = {
        i.code
        for i in _staging(
            workos_jwks_url="https://api.workos.com/sso/jwks/client_a_different_app"
        )
    }
    assert "jwks_client_mismatch" in codes


def test_staging_requires_client_id():
    codes = {i.code for i in _staging(workos_client_id="")}
    assert "client_id_missing" in codes


def test_staging_rejects_malformed_client_id():
    codes = {i.code for i in _staging(workos_client_id="not-a-client-id")}
    assert "client_id_malformed" in codes


def test_local_does_not_enforce_workos_host_contract():
    # Local/e2e use loopback JWKS deliberately; the host/client contract is not
    # applied, and no client_id is required.
    issues = validate_settings(
        environment="e2e",
        database_url="postgresql://helios:helios@localhost:5433/helios",
        cors_origins=["http://localhost:5173"],
        workos_client_id="",
        workos_issuer="http://127.0.0.1:9/",
        workos_jwks_url="http://127.0.0.1:9/jwks",
        helios_e2e_test_mode=True,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert not any(
        i.code
        in {"issuer_contract", "jwks_contract", "jwks_client_mismatch", "client_id_missing"}
        for i in issues
    )
