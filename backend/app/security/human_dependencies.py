"""FastAPI dependencies for WorkOS human authentication.

Separate from the project API-key dependency (security/dependencies.py); the
two credential families never mix. Responses stay generic: 401 for any
credential problem (with WWW-Authenticate: Bearer), 403 for a valid user who is
not yet a member of a workspace (organization). Nothing about other
organizations, JWT internals, JWKS, or the database is revealed.
"""

from __future__ import annotations

import logging

from fastapi import Header, HTTPException

from app.security.api_keys import AuthError
from app.security.workos_auth import HumanAuthContext, authenticate_human

logger = logging.getLogger("helios.auth.human")

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


def _reason_code(reason: str) -> str:
    return _REASON_CODES.get(reason, "auth_rejected")


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX):].strip()
    return token or None


def _dependency(require_org: bool):
    def dependency(
        authorization: str | None = Header(default=None),
    ) -> HumanAuthContext:
        if authorization and not authorization.lower().startswith(_BEARER_PREFIX):
            raise HTTPException(
                status_code=401, detail=_GENERIC_401, headers=_WWW_AUTHENTICATE
            )
        token = _extract_bearer(authorization)
        try:
            return authenticate_human(token, require_org=require_org)
        except AuthError as exc:
            # Structured, credential-free diagnostic. Never logs the token,
            # Authorization header, cookie, email, or any secret.
            logger.info(
                "human auth rejected: reason=%s status=%s",
                _reason_code(exc.reason),
                exc.status_code,
            )
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
