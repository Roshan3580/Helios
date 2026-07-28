"""FastAPI dependencies for WorkOS human authentication.

Separate from the project API-key dependency (security/dependencies.py); the
two credential families never mix. Responses stay generic: 401 for any
credential problem (with WWW-Authenticate: Bearer), 403 for a valid user who is
not yet a member of a workspace (organization). Nothing about other
organizations, JWT internals, JWKS, or the database is revealed.
"""

from __future__ import annotations

import logging

from fastapi import Header, HTTPException, Request

from app.logging_config import AUTH_LOGGER_NAME
from app.security.api_keys import AuthError
from app.security.workos_auth import HumanAuthContext, authenticate_human

logger = logging.getLogger(AUTH_LOGGER_NAME)

_BEARER_PREFIX = "bearer "
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}
_GENERIC_401 = "invalid authentication credentials"
_ORG_403 = (
    "you are not a member of a Helios workspace yet; "
    "create or join a workspace to continue"
)

# Bounded, safe structured reason codes for operator diagnostics. The client
# response stays generic; only these short category codes are logged (never the
# token, Authorization header, cookie, email, or any secret). This is how a
# hosted "signed in but 401 on every API call" failure is attributed to a
# concrete cause (e.g. issuer mismatch vs expired token) without exposing
# credentials.
_REASON_CODES = {
    "missing_token": "auth_missing_token",
    "expired_jwt": "auth_expired_token",
    "wrong_issuer": "auth_invalid_issuer",
    "missing_client_id": "auth_invalid_client_id",
    "wrong_client_id": "auth_invalid_client_id",
    "invalid_signature": "auth_invalid_signature",
    "unknown_signing_key": "auth_invalid_signature",
    "unsupported_algorithm": "auth_invalid_signature",
    "missing_kid": "auth_invalid_signature",
    "malformed_jwt": "auth_invalid_signature",
    "jwks_unavailable": "auth_jwks_failure",
    "missing_org": "auth_missing_org",
    "organization_unavailable": "auth_missing_org",
    "human_auth_not_configured": "auth_not_configured",
    "missing_claims": "auth_invalid_token",
    "missing_sub": "auth_missing_subject",
    "missing_sid": "auth_invalid_token",
}

#: Closed allowlist of everything `_reason_code` may ever return. The raw
#: internal AuthError reason is NEVER logged directly — it only reaches a log
#: line after passing through `_REASON_CODES`, and anything unrecognised
#: collapses to `auth_rejected`. Asserted by tests so a future AuthError reason
#: cannot silently widen what appears in hosted logs.
SAFE_REASONS = frozenset(
    {
        "auth_missing_token",
        "auth_expired_token",
        "auth_invalid_issuer",
        "auth_invalid_client_id",
        "auth_invalid_signature",
        "auth_jwks_failure",
        "auth_missing_org",
        "auth_not_configured",
        "auth_invalid_token",
        "auth_missing_subject",
        "auth_rejected",
    }
)

_FALLBACK_REASON = "auth_rejected"


def _reason_code(reason: str) -> str:
    """Map an internal AuthError reason onto the closed safe allowlist."""
    code = _REASON_CODES.get(reason, _FALLBACK_REASON)
    # Defensive: a mapping edit that introduced an unlisted value would be
    # contained here rather than reaching a hosted log line.
    return code if code in SAFE_REASONS else _FALLBACK_REASON


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX):].strip()
    return token or None


def _safe_path(request: Request | None) -> str:
    """The matched application route path only.

    ONLY ``request.url.path`` is read. The full URL, query string, headers,
    cookies, and client address are deliberately never touched, so no token can
    arrive through a query parameter and no address can be attributed to a user.
    """
    if request is None:
        return "-"
    try:
        return request.url.path or "-"
    except Exception:  # pragma: no cover - defensive; never break auth on logging
        return "-"


def _log_rejection(reason: str, status_code: int, request: Request | None) -> None:
    """Emit exactly one bounded, credential-free rejection line.

    Emitted at WARNING so the record clears Python's default root threshold and
    reaches the hosted stream even if ``configure_auth_logging()`` never ran (see
    app/logging_config.py). Never passes ``exc_info``; the formatter drops
    exception and stack detail structurally as well.
    """
    logger.warning(
        "human auth rejected: reason=%s status=%s path=%s",
        _reason_code(reason),
        status_code,
        _safe_path(request),
    )


def _dependency(require_org: bool):
    def dependency(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> HumanAuthContext:
        if authorization and not authorization.lower().startswith(_BEARER_PREFIX):
            # A non-Bearer scheme previously produced a 401 with no diagnostic
            # at all, leaving the most basic hosted misconfiguration invisible.
            _log_rejection("missing_token", 401, request)
            raise HTTPException(
                status_code=401, detail=_GENERIC_401, headers=_WWW_AUTHENTICATE
            )
        token = _extract_bearer(authorization)
        try:
            return authenticate_human(token, require_org=require_org)
        except AuthError as exc:
            # Structured, credential-free diagnostic. Never logs the token,
            # Authorization header, cookie, email, or any secret.
            _log_rejection(exc.reason, exc.status_code, request)
            if exc.status_code == 403:
                raise HTTPException(status_code=403, detail=_ORG_403)
            raise HTTPException(
                status_code=401, detail=_GENERIC_401, headers=_WWW_AUTHENTICATE
            )

    return dependency


# /v2/user/me works without an organization (onboarding); project/trace routes
# require a linked organization.
require_human = _dependency(require_org=False)
require_org_member = _dependency(require_org=True)
