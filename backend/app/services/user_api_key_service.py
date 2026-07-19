"""Human-facing adapters for project API-key management.

Cryptographic generation and hashing remain in ``app.security.api_keys`` and
``app.services.api_key_service``. This module adds validation, deterministic
listing order, and a browser-safe display identifier derived only from the
non-secret lookup prefix.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models import Project
from app.models_auth import ProjectAPIKey
from app.security.api_keys import KEY_TOKEN_PREFIX, validate_scopes
from app.services.api_key_service import CreatedKey, create_api_key, revoke_api_key

MAX_KEY_NAME_LEN = 128

_KEY_NAME_RE = re.compile(r"^[\w .:@/+_-]+$", re.UNICODE)


class ApiKeyValidationError(ValueError):
    """Raised for invalid key name or scopes."""


def normalize_key_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise ApiKeyValidationError("name must be a string")
    name = raw.strip()
    if not name:
        raise ApiKeyValidationError("name must not be blank")
    if len(name) > MAX_KEY_NAME_LEN:
        raise ApiKeyValidationError(
            f"name must be at most {MAX_KEY_NAME_LEN} characters"
        )
    if not _KEY_NAME_RE.fullmatch(name):
        raise ApiKeyValidationError("name contains unsupported characters")
    return name


def create_project_api_key(
    db: Session,
    *,
    project: Project,
    name: str,
    scopes: list[str],
) -> CreatedKey:
    """Create a scoped project API key. Plaintext is returned once only."""
    normalized_name = normalize_key_name(name)
    try:
        normalized_scopes = validate_scopes(scopes)
    except ValueError as exc:
        raise ApiKeyValidationError(str(exc)) from exc
    return create_api_key(
        db, project=project, name=normalized_name, scopes=normalized_scopes
    )


def list_project_api_keys(db: Session, *, project: Project) -> list[ProjectAPIKey]:
    """List keys for a project: active first, newest first, stable id tie-break."""
    active_first = case((ProjectAPIKey.revoked_at.is_(None), 0), else_=1)
    return list(
        db.scalars(
            select(ProjectAPIKey)
            .where(ProjectAPIKey.project_id == project.id)
            .order_by(
                active_first.asc(),
                ProjectAPIKey.created_at.desc(),
                ProjectAPIKey.id.asc(),
            )
        )
    )


def get_project_api_key(
    db: Session, *, project: Project, key_id
) -> ProjectAPIKey | None:
    """Return a key belonging to ``project``, or None."""
    return db.scalar(
        select(ProjectAPIKey).where(
            ProjectAPIKey.id == key_id,
            ProjectAPIKey.project_id == project.id,
        )
    )


def revoke_project_api_key(db: Session, *, api_key: ProjectAPIKey) -> ProjectAPIKey:
    """Idempotent revoke. Always returns the key in revoked state."""
    revoke_api_key(db, api_key=api_key)
    if api_key.revoked_at is None:
        # Defensive: service should have set this.
        api_key.revoked_at = datetime.now(timezone.utc)
        db.flush()
    return api_key


def display_key_identifier(key_prefix: str) -> str:
    """Non-secret display id based only on the lookup prefix.

    Format: ``hel_proj_<prefix>…`` — the ellipsis marks that the secret
    portion is intentionally omitted and cannot be recovered.
    """
    return f"{KEY_TOKEN_PREFIX}_{key_prefix}…"
