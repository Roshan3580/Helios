"""Test-only E2E helpers: insights seeding under explicit HELIOS_E2E_TEST_MODE."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.e2e.insights_seed import seed_error_rate_regression
from app.models import Project
from app.security.human_dependencies import require_org_member
from app.security.workos_auth import HumanAuthContext

router = APIRouter(prefix="/e2e", tags=["e2e"])


class SeedInsightsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    hours: int = Field(default=24, ge=1, le=168)


class SeedInsightsResponse(BaseModel):
    project_id: UUID
    current_traces: int
    baseline_traces: int
    error_traces: int


def _is_loopback(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    return host in {"127.0.0.1", "localhost", "::1"}


def assert_e2e_backend_allowed() -> None:
    settings = get_settings()
    if not settings.helios_e2e_test_mode:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    jwks = settings.workos_jwks_url_resolved
    issuer = settings.workos_issuer_resolved
    if not jwks or not _is_loopback(jwks):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if not issuer or not _is_loopback(issuer):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if settings.openai_api_key.get_secret_value():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _resolve_project(db: Session, auth: HumanAuthContext, project_ref: str) -> Project:
    org_id = uuid.UUID(auth.local_org_id)
    stmt = select(Project).where(Project.organization_id == org_id)
    try:
        stmt = stmt.where(Project.id == uuid.UUID(project_ref))
    except ValueError:
        stmt = stmt.where(Project.slug == project_ref)
    project = db.scalar(stmt)
    if project is None:
        raise HTTPException(status_code=404, detail="Not found")
    return project


@router.post(
    "/seed-insights",
    response_model=SeedInsightsResponse,
    status_code=status.HTTP_201_CREATED,
)
def seed_insights(
    body: SeedInsightsRequest,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> SeedInsightsResponse:
    """Insert canonical otel rows that trigger at least one project finding."""
    assert_e2e_backend_allowed()
    project = _resolve_project(db, auth, str(body.project_id))
    counts = seed_error_rate_regression(db, project=project, hours=body.hours)
    db.commit()
    return SeedInsightsResponse(
        project_id=project.id,
        current_traces=counts["current_traces"],
        baseline_traces=counts["baseline_traces"],
        error_traces=counts["error_traces"],
    )


def include_e2e_router(app) -> None:
    settings = get_settings()
    if settings.helios_e2e_test_mode:
        app.include_router(router, prefix="/v2")
