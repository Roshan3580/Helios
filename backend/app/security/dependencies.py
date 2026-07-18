"""Reusable FastAPI dependency for project-API-key authentication.

Usage on a canonical route:

    auth: AuthContext = Depends(require_scope(SCOPE_TRACES_READ))

Parsing lives here once; routers never re-parse the Authorization header.
"""

from __future__ import annotations

from typing import Callable

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.security.api_keys import AuthContext, AuthError
from app.security.service import authenticate

_BEARER_PREFIX = "bearer "
_WWW_AUTHENTICATE = {"WWW-Authenticate": "Bearer"}


def _extract_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    if not authorization.lower().startswith(_BEARER_PREFIX):
        return None
    token = authorization[len(_BEARER_PREFIX):].strip()
    return token or None


def require_scope(required_scope: str) -> Callable[..., AuthContext]:
    def dependency(
        authorization: str | None = Header(default=None),
        db: Session = Depends(get_db),
    ) -> AuthContext:
        # A malformed/absent Bearer header is a 401 (challenge), not a parse
        # of a real token — but keep the response generic either way.
        if authorization and not authorization.lower().startswith(_BEARER_PREFIX):
            raise HTTPException(
                status_code=401,
                detail="invalid authentication credentials",
                headers=_WWW_AUTHENTICATE,
            )
        token = _extract_bearer(authorization)
        try:
            return authenticate(db, token, required_scope)
        except AuthError as exc:
            if exc.status_code == 403:
                raise HTTPException(
                    status_code=403,
                    detail="the provided key lacks the required scope",
                )
            raise HTTPException(
                status_code=401,
                detail="invalid authentication credentials",
                headers=_WWW_AUTHENTICATE,
            )

    return dependency
