"""Staging/production deployment contract validation (no secrets in errors)."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

STAGING_LIKE = frozenset({"staging", "production"})
LOCAL_LIKE = frozenset({"local", "test", "e2e", "development"})


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str


def _is_https(url: str) -> bool:
    try:
        return urlparse(url).scheme == "https"
    except ValueError:
        return False


def _is_loopback_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def _db_name(database_url: str) -> str:
    try:
        return (urlparse(database_url).path or "").lstrip("/").lower()
    except ValueError:
        return ""


def sanitize_message(message: str) -> str:
    """Strip credential-like substrings from operator-facing messages."""
    # Never echo query strings or userinfo from URLs.
    out = message
    for needle in ("postgresql://", "postgres://", "sk_", "hel_proj_", "eyJ"):
        if needle in out:
            out = out.replace(needle, "[redacted]")
    return out


def validate_settings(
    *,
    environment: str,
    database_url: str,
    cors_origins: list[str],
    workos_issuer: str,
    workos_jwks_url: str,
    helios_e2e_test_mode: bool,
    helios_demo_mode: bool,
    narrative_enabled: bool,
    allow_third_party: bool,
    analyst_provider: str,
    openai_key_present: bool,
) -> list[ValidationIssue]:
    """Return validation issues for the given settings snapshot.

    Never include secret values in issue messages.
    Unknown environments are always fatal — no local/staging/production
    checks are skipped for unknown environments.
    """
    env = (environment or "local").strip().lower()
    issues: list[ValidationIssue] = []

    if env not in STAGING_LIKE | LOCAL_LIKE:
        issues.append(
            ValidationIssue(
                "unknown_environment",
                f"Unknown HELIOS_ENVIRONMENT={env!r}; expected local|test|e2e|staging|production",
            )
        )
        # Unknown environments fail closed: all subsequent checks apply equally.
        # Treat unknown as staging-like (unsafe, require all checks to pass).

    # Apply staging/production checks to staging-like AND unknown environments
    is_staging_like_or_unknown = env in STAGING_LIKE or env not in LOCAL_LIKE
    if is_staging_like_or_unknown:
        if helios_e2e_test_mode:
            issues.append(
                ValidationIssue(
                    "e2e_forbidden",
                    "HELIOS_E2E_TEST_MODE must be false in staging/production",
                )
            )

        if helios_demo_mode:
            issues.append(
                ValidationIssue(
                    "demo_mode_forbidden",
                    "HELIOS_DEMO_MODE must be false in staging/production; "
                    "legacy/demo APIs cannot run there",
                )
            )

        db = _db_name(database_url)
        if not database_url.strip():
            issues.append(ValidationIssue("database_missing", "DATABASE_URL is required"))
        elif db in {"helios_test", "test"} or db.endswith("_test"):
            issues.append(
                ValidationIssue(
                    "database_is_test",
                    "DATABASE_URL must not point at the isolated test database in staging/production",
                )
            )

        if not cors_origins:
            issues.append(
                ValidationIssue("cors_empty", "CORS_ORIGINS must list the staging frontend origin")
            )
        for origin in cors_origins:
            if origin == "*":
                issues.append(
                    ValidationIssue("cors_wildcard", "Wildcard CORS is forbidden in staging/production")
                )
            elif _is_loopback_url(origin):
                issues.append(
                    ValidationIssue(
                        "cors_loopback",
                        "Loopback CORS origins are forbidden in staging/production",
                    )
                )
            elif not _is_https(origin):
                issues.append(
                    ValidationIssue(
                        "cors_https",
                        "CORS_ORIGINS entries must use HTTPS in staging/production",
                    )
                )

        if not workos_issuer or not _is_https(workos_issuer):
            issues.append(
                ValidationIssue(
                    "issuer_https",
                    "WORKOS_ISSUER (or derived issuer) must be HTTPS in staging/production",
                )
            )
        elif _is_loopback_url(workos_issuer):
            issues.append(
                ValidationIssue(
                    "issuer_loopback",
                    "Loopback WORKOS_ISSUER is forbidden in staging/production",
                )
            )

        if not workos_jwks_url or not _is_https(workos_jwks_url):
            issues.append(
                ValidationIssue(
                    "jwks_https",
                    "WORKOS_JWKS_URL (or derived JWKS) must be HTTPS in staging/production",
                )
            )
        elif _is_loopback_url(workos_jwks_url):
            issues.append(
                ValidationIssue(
                    "jwks_loopback",
                    "Loopback WORKOS_JWKS_URL is forbidden in staging/production",
                )
            )

    if narrative_enabled and allow_third_party:
        if (analyst_provider or "").strip().lower() == "openai" and not openai_key_present:
            issues.append(
                ValidationIssue(
                    "openai_key_required",
                    "OPENAI_API_KEY is required when narrative and third-party transmission are enabled",
                )
            )
    # When narrative is disabled, OpenAI key is optional (must not be required).

    return issues


def allow_loopback_cors_regex(environment: str, e2e_mode: bool) -> bool:
    env = (environment or "local").strip().lower()
    return e2e_mode or env in {"local", "test", "e2e", "development"}
