"""Deployment contract validation unit tests."""

from __future__ import annotations

from app.deployment_validation import sanitize_message, validate_settings


def test_local_allows_loopback_defaults():
    issues = validate_settings(
        environment="local",
        database_url="postgresql://helios:helios@localhost:5433/helios",
        cors_origins=["http://localhost:5173"],
        workos_issuer="http://127.0.0.1:9/",
        workos_jwks_url="http://127.0.0.1:9/jwks",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert issues == []


def test_staging_rejects_e2e_and_loopback():
    issues = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios_staging",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="http://127.0.0.1:9/",
        workos_jwks_url="http://127.0.0.1:9/jwks",
        helios_e2e_test_mode=True,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    codes = {i.code for i in issues}
    assert "e2e_forbidden" in codes
    assert "issuer_loopback" in codes or "issuer_https" in codes
    assert "jwks_loopback" in codes or "jwks_https" in codes


def test_staging_rejects_wildcard_and_test_db():
    issues = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@localhost:5434/helios_test",
        cors_origins=["*"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    codes = {i.code for i in issues}
    assert "cors_wildcard" in codes
    assert "database_is_test" in codes


def test_staging_requires_https_cors_and_workos():
    issues = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert issues == []


def test_openai_required_only_when_narrative_enabled():
    ok = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="openai",
        openai_key_present=False,
    )
    assert ok == []

    bad = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=True,
        allow_third_party=True,
        analyst_provider="openai",
        openai_key_present=False,
    )
    assert any(i.code == "openai_key_required" for i in bad)


def test_sanitize_message_redacts_prefixes():
    msg = sanitize_message("bad postgresql://user:pass@host/db and sk_live_xxx")
    assert "postgresql://" not in msg
    assert "sk_live" not in msg
    assert "[redacted]" in msg


def test_staging_rejects_demo_mode():
    issues = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=True,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert any(i.code == "demo_mode_forbidden" for i in issues)


def test_production_rejects_demo_mode():
    issues = validate_settings(
        environment="production",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios.example.com"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=True,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert any(i.code == "demo_mode_forbidden" for i in issues)


def test_staging_allows_demo_mode_false():
    issues = validate_settings(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert issues == []


def test_production_allows_demo_mode_false():
    issues = validate_settings(
        environment="production",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios.example.com"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert issues == []


def test_local_allows_demo_mode_true():
    issues = validate_settings(
        environment="local",
        database_url="postgresql://helios:helios@localhost:5433/helios",
        cors_origins=["http://localhost:5173"],
        workos_issuer="http://127.0.0.1:9/",
        workos_jwks_url="http://127.0.0.1:9/jwks",
        helios_e2e_test_mode=False,
        helios_demo_mode=True,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert issues == []


def test_unknown_environment_prod_is_fatal():
    """Unknown environment 'prod' must fail closed (H1)."""
    issues = validate_settings(
        environment="prod",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://helios-staging.example.onrender.com"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert any(i.code == "unknown_environment" for i in issues)


def test_unknown_environment_with_demo_mode_fails_closed():
    """Unknown environment must fail closed even when combined with demo_mode (H1)."""
    issues = validate_settings(
        environment="live",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://example.com"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=True,  # try to sneak demo mode in
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    # Must include unknown_environment; demo_mode check should also apply
    assert any(i.code == "unknown_environment" for i in issues)
    assert any(i.code == "demo_mode_forbidden" for i in issues)


def test_unknown_environment_production_variant_fails():
    """Arbitrary unknown environment like 'production-1' must fail closed."""
    issues = validate_settings(
        environment="production-1",
        database_url="postgresql://u:p@db.example/helios",
        cors_origins=["https://example.com"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert any(i.code == "unknown_environment" for i in issues)


def _staging_workos(**overrides):
    """Valid staging settings with overridable WorkOS issuer/JWKS."""
    base = dict(
        environment="staging",
        database_url="postgresql://u:p@db.example/helios_staging",
        cors_origins=["https://helios-staging.example.vercel.app"],
        workos_issuer="https://api.workos.com/user_management/client_x",
        workos_jwks_url="https://api.workos.com/sso/jwks/client_x",
        helios_e2e_test_mode=False,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    base.update(overrides)
    return validate_settings(**base)


def test_staging_accepts_official_workos_contract():
    # Checkpoint 25: the official WorkOS issuer/JWKS contract is fully valid.
    assert _staging_workos() == []


def test_staging_rejects_non_workos_issuer_host():
    codes = {i.code for i in _staging_workos(
        workos_issuer="https://evil.example.com/user_management/client_x"
    )}
    assert "issuer_contract" in codes


def test_staging_rejects_wrong_issuer_path():
    codes = {i.code for i in _staging_workos(
        workos_issuer="https://api.workos.com/wrong_path/client_x"
    )}
    assert "issuer_contract" in codes


def test_staging_rejects_non_workos_jwks_host():
    codes = {i.code for i in _staging_workos(
        workos_jwks_url="https://cdn.example.com/sso/jwks/client_x"
    )}
    assert "jwks_contract" in codes


def test_staging_rejects_wrong_jwks_path():
    codes = {i.code for i in _staging_workos(
        workos_jwks_url="https://api.workos.com/keys/client_x"
    )}
    assert "jwks_contract" in codes


def test_local_does_not_enforce_workos_host_contract():
    # Local/e2e use loopback JWKS deliberately; the host contract is not applied.
    issues = validate_settings(
        environment="e2e",
        database_url="postgresql://helios:helios@localhost:5433/helios",
        cors_origins=["http://localhost:5173"],
        workos_issuer="http://127.0.0.1:9/",
        workos_jwks_url="http://127.0.0.1:9/jwks",
        helios_e2e_test_mode=True,
        helios_demo_mode=False,
        narrative_enabled=False,
        allow_third_party=False,
        analyst_provider="",
        openai_key_present=False,
    )
    assert not any(i.code in {"issuer_contract", "jwks_contract"} for i in issues)
