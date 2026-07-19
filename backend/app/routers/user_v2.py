"""Human-authenticated (WorkOS JWT) routes for browsers.

Machine routes (/v1/otlp/traces and API-key /v2/traces) are untouched; this
family never calls the API-key dependency and never mints project keys. The
organization comes exclusively from the verified JWT's org_id; projects are
readable only when owned by that organization. Cross-organization lookups are
404 (indistinguishable from missing), never 403, to avoid information leaks.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project
from app.schemas_dashboard import ProjectDashboardRead
from app.schemas_user import UserMeRead, UserOrganizationRead, UserProjectRead
from app.schemas_v2 import OtelTraceDetailRead, OtelTraceSummaryRead
from app.security.human_dependencies import require_human, require_org_member
from app.security.workos_auth import HumanAuthContext
from app.services import otel_dashboard_service, otel_trace_service

router = APIRouter(prefix="/user", tags=["user-v2"])


@router.get("/me", response_model=UserMeRead)
def get_me(auth: HumanAuthContext = Depends(require_human)) -> dict:
    return {
        "user_id": auth.local_user_id,
        "workos_user_id": auth.workos_user_id,
        "organization": UserOrganizationRead(
            id=auth.local_org_id,
            workos_org_id=auth.workos_org_id,
            slug=auth.organization_slug,
            name=auth.organization_name,
            linked=auth.local_org_id is not None,
        ),
        "role": auth.role,
        "permissions": list(auth.permissions),
    }


@router.get("/projects", response_model=list[UserProjectRead])
def list_my_projects(
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .where(Project.organization_id == uuid.UUID(auth.local_org_id))
            .order_by(Project.slug)
        )
    )


def _resolve_project(db: Session, auth: HumanAuthContext, project_ref: str) -> Project:
    """Resolve by project UUID or slug, scoped to the caller's organization.

    A project in another organization (or nonexistent) is a 404 either way.
    """
    org_id = uuid.UUID(auth.local_org_id)
    stmt = select(Project).where(Project.organization_id == org_id)
    try:
        stmt = stmt.where(Project.id == uuid.UUID(project_ref))
    except ValueError:
        stmt = stmt.where(Project.slug == project_ref)
    project = db.scalar(stmt)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_ref}' not found")
    return project


@router.get(
    "/projects/{project_ref}/dashboard",
    response_model=ProjectDashboardRead,
)
def get_project_dashboard(
    project_ref: str,
    hours: int = Query(default=24, ge=1, le=720),
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> dict:
    """Organization-authorized OTel aggregates for the selected project.

    Window is evaluated on trace ``start_time``. There is no cost field and no
    fabricated token/model estimates — only stored GenAI attributes.
    """
    project = _resolve_project(db, auth, project_ref)
    return otel_dashboard_service.get_project_dashboard(
        db, project=project, hours=hours
    )


@router.get("/projects/{project_ref}/traces", response_model=list[OtelTraceSummaryRead])
def list_project_traces(
    project_ref: str,
    limit: int = Query(default=50, ge=1, le=200),
    service_name: str | None = Query(default=None),
    has_errors: bool | None = Query(default=None),
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> list[dict]:
    project = _resolve_project(db, auth, project_ref)
    return otel_trace_service.list_traces(
        db,
        project_slug=project.slug,
        limit=limit,
        service_name=service_name,
        has_errors=has_errors,
    )


@router.get(
    "/projects/{project_ref}/traces/{trace_id}", response_model=OtelTraceDetailRead
)
def get_project_trace(
    project_ref: str,
    trace_id: str,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> dict:
    project = _resolve_project(db, auth, project_ref)
    detail = otel_trace_service.get_trace_detail(
        db, project_slug=project.slug, trace_id=trace_id
    )
    if not detail:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return detail
