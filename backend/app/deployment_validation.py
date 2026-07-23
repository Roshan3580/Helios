"""Staging/production deployment contract validation (no secrets in errors)."""

from __future__ import annotations

import re
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


# Official WorkOS AuthKit access-token verification contract (see config.py
# derivation). AuthKit access tokens are issued by the WorkOS API root
# (``iss=https://api.workos.com``, no path) and verified against an
# application-specific JWKS at ``/sso/jwks/<client_id>`` on the same host.
# The prior ``/user_management/<client_id>`` issuer was incorrect: no WorkOS
# access token carries it, so a verifier expecting it rejects every valid
# token. A custom WorkOS auth domain may set an explicit non-workos issuer,
# but the JWKS is always served from api.workos.com.
_WORKOS_HOST = "api.workos.com"
_WORKOS_JWKS_PATH_PREFIX = "/sso/jwks/"
# WorkOS client ids look like ``client_<alphanumeric/underscore>``. Kept
# permissive enough for documented placeholders (e.g. client_staging_example)
# while rejecting empty/whitespace/obviously-wrong values.
_CLIENT_ID_RE = re.compile(r"client_[0-9A-Za-z_]{3,}\Z")


def _url_parts(url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(url)
        return (parsed.hostname or "").lower(), parsed.path or ""
    except ValueError:
        return "", ""


def _url_has_credentials_or_extras(url: str) -> bool:
    """True if a URL carries userinfo, a query string, or a fragment."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return True
    return bool(parsed.username or parsed.password or parsed.query or parsed.fragment)


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
    workos_client_id: str,
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

        # WorkOS client id: required and well-formed in staging/production, so
        # the verifier can enforce application isolation (the client_id claim).
        client_id = (workos_client_id or "").strip()
        if not client_id:
            issues.append(
                ValidationIssue(
                    "client_id_missing",
                    "WORKOS_CLIENT_ID is required in staging/production",
                )
            )
        elif not _CLIENT_ID_RE.match(client_id):
            issues.append(
                ValidationIssue(
                    "client_id_malformed",
                    "WORKOS_CLIENT_ID must look like client_<id>",
                )
            )

        # WorkOS issuer contract. The official AuthKit access-token issuer is
        # exactly https://api.workos.com (no path). An explicit custom WorkOS
        # auth domain (a different host) is permitted, but must be a clean
        # HTTPS origin. The api.workos.com host must NOT carry a path — in
        # particular /user_management/<client_id> is NOT the token issuer and
        # is the exact misconfiguration behind a hosted "signed in but every
        # API call is 401" loop.
        if workos_issuer and _is_https(workos_issuer) and not _is_loopback_url(workos_issuer):
            host, path = _url_parts(workos_issuer)
            if _url_has_credentials_or_extras(workos_issuer):
                issues.append(
                    ValidationIssue(
                        "issuer_contract",
                        "WORKOS_ISSUER must not contain credentials, a query string, or a fragment",
                    )
                )
            elif host == _WORKOS_HOST and path.rstrip("/"):
                issues.append(
                    ValidationIssue(
                        "issuer_contract",
                        f"WORKOS_ISSUER for {_WORKOS_HOST} must be exactly "
                        f"https://{_WORKOS_HOST} (no path); the access-token issuer is "
                        "not /user_management/<client_id>",
                    )
                )
            # A non-workos host is treated as a legitimate custom auth domain.

        # WorkOS JWKS contract: always served from api.workos.com at
        # /sso/jwks/<client_id>, even for custom auth domains. The embedded
        # client id must match WORKOS_CLIENT_ID.
        if workos_jwks_url and _is_https(workos_jwks_url) and not _is_loopback_url(workos_jwks_url):
            host, path = _url_parts(workos_jwks_url)
            if _url_has_credentials_or_extras(workos_jwks_url):
                issues.append(
                    ValidationIssue(
                        "jwks_contract",
                        "WORKOS_JWKS_URL must not contain credentials, a query string, or a fragment",
                    )
                )
            elif host != _WORKOS_HOST or not path.startswith(_WORKOS_JWKS_PATH_PREFIX):
                issues.append(
                    ValidationIssue(
                        "jwks_contract",
                        "WORKOS_JWKS_URL must be "
                        f"https://{_WORKOS_HOST}{_WORKOS_JWKS_PATH_PREFIX}<client_id> "
                        "(official WorkOS AuthKit contract)",
                    )
                )
            else:
                jwks_client_id = path[len(_WORKOS_JWKS_PATH_PREFIX):].strip("/")
                if client_id and jwks_client_id and jwks_client_id != client_id:
                    issues.append(
                        ValidationIssue(
                            "jwks_client_mismatch",
                            "WORKOS_JWKS_URL client id must match WORKOS_CLIENT_ID",
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
