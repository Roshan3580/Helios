"""Administrative service for organization mapping (used by the CLI and tests).

Maps WorkOS organizations to local Helios organizations and assigns projects.
No WorkOS API key is needed — these are purely local database mappings.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Project
from app.models_identity import Organization

# WorkOS org IDs look like org_<ULID-ish>; validate loosely to avoid
# overfitting undocumented formats while rejecting obvious junk.
_WORKOS_ORG_ID_RE = re.compile(r"^org_[A-Za-z0-9]{5,60}$")


def validate_workos_org_id(value: str) -> str:
    value = value.strip()
    if not _WORKOS_ORG_ID_RE.match(value):
        raise ValueError(
            f"'{value}' does not look like a WorkOS organization ID (org_...)"
        )
    return value


def create_organization(
    db: Session, *, workos_org_id: str, slug: str, name: str
) -> tuple[Organization, bool]:
    """Create or return the org for a WorkOS ID. Returns (org, created)."""
    workos_org_id = validate_workos_org_id(workos_org_id)
    existing = db.scalar(
        select(Organization).where(Organization.workos_org_id == workos_org_id)
    )
    if existing:
        return existing, False
    slug = slug.strip().lower()
    if not slug:
        raise ValueError("slug is required")
    if db.scalar(select(Organization).where(Organization.slug == slug)):
        raise ValueError(f"organization slug '{slug}' is already taken")
    organization = Organization(workos_org_id=workos_org_id, slug=slug, name=name.strip() or slug)
    db.add(organization)
    db.flush()
    return organization, True


def assign_project(
    db: Session, *, organization: Organization, project_slug: str
) -> tuple[Project, bool]:
    """Assign a project to an organization. Returns (project, changed).

    A project already owned by another organization is refused (a project can
    belong to exactly one organization). Re-assigning to the same organization
    is an idempotent no-op. Project API keys are never touched.
    """
    project = db.scalar(select(Project).where(Project.slug == project_slug))
    if project is None:
        raise ValueError(f"project '{project_slug}' not found")
    if project.organization_id is not None:
        if project.organization_id == organization.id:
            return project, False
        raise ValueError(
            f"project '{project_slug}' is already assigned to another organization"
        )
    project.organization_id = organization.id
    db.flush()
    return project, True


def list_organizations(db: Session) -> list[tuple[Organization, list[Project]]]:
    organizations = list(
        db.scalars(select(Organization).order_by(Organization.slug))
    )
    result = []
    for organization in organizations:
        projects = list(
            db.scalars(
                select(Project)
                .where(Project.organization_id == organization.id)
                .order_by(Project.slug)
            )
        )
        result.append((organization, projects))
    return result
