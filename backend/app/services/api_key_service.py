"""Administrative service for project API keys (used by the CLI and tests).

Persists only prefix/hash/metadata. The plaintext token is returned once from
create_api_key and never stored or logged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.models_auth import ProjectAPIKey
from app.security.api_keys import GeneratedKey, generate_api_key, validate_scopes


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CreatedKey:
    api_key: ProjectAPIKey
    token: str  # plaintext, show once


def get_or_create_project(
    db: Session,
    *,
    slug: str,
    name: str | None = None,
    environment: str = "production",
) -> Project:
    """Explicit administrative project resolution (create if absent).

    Project creation is confined to this admin path; the OTLP ingestion path
    no longer creates projects.
    """
    project = db.scalar(select(Project).where(Project.slug == slug))
    if project:
        return project
    project = Project(
        slug=slug,
        name=name or slug.replace("-", " ").title(),
        environment=environment,
    )
    db.add(project)
    db.flush()
    return project


def create_api_key(
    db: Session,
    *,
    project: Project,
    name: str,
    scopes: list[str],
    expires_at: datetime | None = None,
) -> CreatedKey:
    normalized_scopes = validate_scopes(scopes)
    generated: GeneratedKey = generate_api_key()
    api_key = ProjectAPIKey(
        project_id=project.id,
        name=name,
        key_prefix=generated.key_prefix,
        key_hash=generated.key_hash,
        scopes=normalized_scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    db.flush()
    return CreatedKey(api_key=api_key, token=generated.token)


def list_api_keys(db: Session, *, project: Project) -> list[ProjectAPIKey]:
    return list(
        db.scalars(
            select(ProjectAPIKey)
            .where(ProjectAPIKey.project_id == project.id)
            .order_by(ProjectAPIKey.created_at.asc())
        )
    )


def revoke_api_key(db: Session, *, api_key: ProjectAPIKey) -> bool:
    """Revoke a key. Returns True if newly revoked, False if already revoked.

    Historical metadata is preserved (no row deletion).
    """
    if api_key.revoked_at is not None:
        return False
    api_key.revoked_at = _utc_now()
    db.flush()
    return True
