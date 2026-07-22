"""Human-facing project creation inside an authorized organization.

Slug uniqueness is currently global (``projects.slug`` UNIQUE). Duplicate
slugs therefore conflict across organizations until a future migration
changes that constraint. Creation never accepts client-supplied IDs or
organization overrides.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Project
from app.models_identity import Organization

# Match Project.name / Project.slug column lengths.
MAX_PROJECT_NAME_LEN = 255
MAX_PROJECT_SLUG_LEN = 128

_ALLOWED_ENVIRONMENTS = frozenset({"production", "staging", "development", "test"})

# Reject slugs that collide with product routes or reserved words.
_RESERVED_SLUGS = frozenset(
    {
        "app",
        "api",
        "admin",
        "me",
        "settings",
        "dashboard",
        "traces",
        "insights",
        "getting-started",
        "v1",
        "v2",
        "otlp",
        "health",
        "null",
        "undefined",
        "new",
        "create",
    }
)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProjectValidationError(ValueError):
    """Raised for invalid project name/slug/environment input."""


class ProjectConflictError(Exception):
    """Raised when a project slug already exists (global uniqueness)."""


@dataclass(frozen=True)
class CreateProjectInput:
    name: str
    slug: str
    environment: str = "production"


def normalize_project_name(raw: str) -> str:
    if not isinstance(raw, str):
        raise ProjectValidationError("name must be a string")
    name = raw.strip()
    if not name:
        raise ProjectValidationError("name must not be blank")
    if len(name) > MAX_PROJECT_NAME_LEN:
        raise ProjectValidationError(
            f"name must be at most {MAX_PROJECT_NAME_LEN} characters"
        )
    return name


def normalize_project_slug(raw: str) -> str:
    if not isinstance(raw, str):
        raise ProjectValidationError("slug must be a string")
    slug = raw.strip().lower()
    if not slug:
        raise ProjectValidationError("slug must not be blank")
    if len(slug) > MAX_PROJECT_SLUG_LEN:
        raise ProjectValidationError(
            f"slug must be at most {MAX_PROJECT_SLUG_LEN} characters"
        )
    if slug.startswith("-") or slug.endswith("-"):
        raise ProjectValidationError("slug must not start or end with a hyphen")
    if "--" in slug:
        raise ProjectValidationError("slug must not contain consecutive hyphens")
    if not _SLUG_RE.fullmatch(slug):
        raise ProjectValidationError(
            "slug may contain only lowercase letters, numbers, and single hyphens"
        )
    if slug in _RESERVED_SLUGS:
        raise ProjectValidationError("slug is reserved")
    return slug


def normalize_environment(raw: str | None) -> str:
    if raw is None:
        return "production"
    if not isinstance(raw, str):
        raise ProjectValidationError("environment must be a string")
    value = raw.strip().lower()
    if value not in _ALLOWED_ENVIRONMENTS:
        raise ProjectValidationError(
            "environment must be one of: "
            + ", ".join(sorted(_ALLOWED_ENVIRONMENTS))
        )
    return value


def create_project_for_organization(
    db: Session,
    *,
    organization: Organization,
    name: str,
    slug: str,
    environment: str | None = None,
) -> Project:
    """Create a project owned by ``organization``.

    Raises:
        ProjectValidationError: invalid name/slug/environment
        ProjectConflictError: slug already taken (globally unique today)
    """
    normalized_name = normalize_project_name(name)
    normalized_slug = normalize_project_slug(slug)
    normalized_env = normalize_environment(environment)

    existing = db.scalar(select(Project).where(Project.slug == normalized_slug))
    if existing is not None:
        raise ProjectConflictError("A project with this slug already exists")

    project = Project(
        id=uuid.uuid4(),
        slug=normalized_slug,
        name=normalized_name,
        environment=normalized_env,
        organization_id=organization.id,
    )
    db.add(project)
    try:
        db.flush()
    except IntegrityError as exc:
        # Race against the unique slug constraint; keep the message generic.
        raise ProjectConflictError("A project with this slug already exists") from exc
    return project
