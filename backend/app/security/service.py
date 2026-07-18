"""Authenticate a bearer token against project_api_keys and enforce scope.

last_used_at strategy
---------------------
On successful authentication the key's last_used_at is updated in a dedicated
short-lived session, committed immediately and independently of the request's
session. This decouples audit bookkeeping from request outcome:

- read routes never commit their request session, yet last_used_at is still
  recorded;
- an ingest route that rolls back on failure does not roll back last_used_at
  (the key WAS used to authenticate successfully).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models_auth import ProjectAPIKey
from app.security.api_keys import AuthContext, AuthError, parse_lookup_prefix, verify_token

logger = logging.getLogger("helios.auth")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _touch_last_used(api_key_id) -> None:
    """Record last_used_at in an isolated transaction; never fatal."""
    try:
        with SessionLocal() as session:
            key = session.get(ProjectAPIKey, api_key_id)
            if key is not None:
                key.last_used_at = _utc_now()
                session.commit()
    except Exception:  # bookkeeping must not break an authenticated request
        logger.warning("failed to update last_used_at for api key")


def authenticate(db: Session, token: str | None, required_scope: str) -> AuthContext:
    """Validate a token and required scope, returning a typed AuthContext.

    Raises AuthError(401) for any credential problem (missing/malformed/
    unknown/mismatch/revoked/expired) with an internal `reason` for logging;
    the caller returns a generic message so key state is never revealed.
    Raises AuthError(403) when the key is valid but lacks the scope.
    """
    if not token:
        logger.info("auth reject: missing bearer token")
        raise AuthError("missing_token", status_code=401)

    lookup_prefix = parse_lookup_prefix(token)
    if lookup_prefix is None:
        logger.info("auth reject: malformed token")
        raise AuthError("malformed_token", status_code=401)

    key = db.scalar(select(ProjectAPIKey).where(ProjectAPIKey.key_prefix == lookup_prefix))
    if key is None:
        logger.info("auth reject: unknown key prefix")
        raise AuthError("unknown_key", status_code=401)

    # Constant-time hash comparison regardless of prefix existence above.
    if not verify_token(token, key.key_hash):
        logger.info("auth reject: hash mismatch (key id=%s)", key.id)
        raise AuthError("hash_mismatch", status_code=401)

    if key.revoked_at is not None:
        logger.info("auth reject: revoked key (key id=%s)", key.id)
        raise AuthError("revoked", status_code=401)

    if key.expires_at is not None and key.expires_at <= _utc_now():
        logger.info("auth reject: expired key (key id=%s)", key.id)
        raise AuthError("expired", status_code=401)

    scopes = tuple(key.scopes or ())
    if required_scope not in scopes:
        logger.info(
            "auth reject: missing scope %s (key id=%s)", required_scope, key.id
        )
        raise AuthError("missing_scope", status_code=403)

    project = key.project
    context = AuthContext(
        api_key_id=str(key.id),
        project_id=str(project.id),
        project_slug=project.slug,
        project_name=project.name,
        scopes=scopes,
        environment=project.environment,
    )

    _touch_last_used(key.id)
    return context
