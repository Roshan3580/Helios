"""FastAPI dependencies for WorkOS human authentication.

Separate from the project API-key dependency (security/dependencies.py); the
two credential families never mix. Responses stay generic: 401 for any
credential problem (with WWW-Authenticate: Bearer), 403 for a valid user who is
not yet a member of a workspace (organization). Nothing about other
organizations, JWT internals, JWKS, or the database is revealed.
"""

from __future__ import annotations

from fastapi import Header, HTTPException

from app.security.api_keys import AuthError
from app.security.workos_auth import HumanAuthContext, authenticate_human

_BEARER_PREFIX = "bearer "
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}
_GENERIC_401 = "invalid authentication credentials"
_ORG_403 = (
    "you are not a member of a Helios workspace yet; "
    "create or join a workspace to continue"
)


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
