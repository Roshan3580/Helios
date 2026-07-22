"""Human-authenticated (WorkOS JWT) routes for browsers.

Machine routes (/v1/otlp/traces and API-key /v2/traces) are untouched; this
family never calls the API-key dependency for authorization. Project API keys
are minted only through the dedicated human create-key endpoint below, and
the plaintext is returned exactly once. The organization comes exclusively
from the verified JWT's org_id; projects are readable only when owned by that
organization. Cross-organization lookups are 404 (indistinguishable from
missing), never 403, to avoid information leaks.

Any authenticated member of the active linked WorkOS organization currently
has organization-wide access to that organization's projects and project
API-key management. Finer-grained project roles are deferred.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analyst import AnalystValidationError
from app.database import get_db
from app.models import Project
from app.models_identity import Organization
from app.schemas_analysis import TraceAnalysisRead, TraceAnalysisRequest
from app.schemas_dashboard import ProjectDashboardRead
from app.schemas_project_analysis import ProjectAnalysisRead, ProjectAnalysisRequest
from app.schemas_project_keys import (
    CreatedProjectApiKeyRead,
    CreateProjectApiKeyRequest,
    CreateUserProjectRequest,
    ProjectApiKeyMetadataRead,
)
from app.schemas_user import UserMeRead, UserOrganizationRead, UserProjectRead
from app.schemas_v2 import OtelTraceDetailRead, OtelTraceSummaryRead
from app.security.human_dependencies import require_human, require_org_member
from app.security.workos_auth import HumanAuthContext
from app.services import (
    otel_dashboard_service,
    otel_trace_service,
    project_analysis_service,
    trace_analysis_service,
    user_api_key_service,
    user_project_service,
)
from app.services.user_api_key_service import ApiKeyValidationError
from app.services.user_project_service import (
    ProjectConflictError,
    ProjectValidationError,
)

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


@router.post("/projects", response_model=UserProjectRead, status_code=201)
def create_my_project(
    body: CreateUserProjectRequest,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> Project:
    """Create a project inside the active linked WorkOS organization.

    Organization cannot be overridden by body or query parameters. Slug
    uniqueness is currently global (see ``projects.slug`` UNIQUE).
    """
    organization = _require_organization(db, auth)
    try:
        project = user_project_service.create_project_for_organization(
            db,
            organization=organization,
            name=body.name,
            slug=body.slug,
            environment=body.environment,
        )
    except ProjectValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProjectConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    db.refresh(project)
    return project


@router.get(
    "/projects/{project_ref}/api-keys",
    response_model=list[ProjectApiKeyMetadataRead],
)
def list_project_api_keys(
    project_ref: str,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> list[ProjectApiKeyMetadataRead]:
    """List redacted project API keys. Never includes plaintext or hash."""
    project = _resolve_project(db, auth, project_ref)
    keys = user_api_key_service.list_project_api_keys(db, project=project)
    return [ProjectApiKeyMetadataRead.model_validate(key) for key in keys]


@router.post(
    "/projects/{project_ref}/api-keys",
    response_model=CreatedProjectApiKeyRead,
    status_code=201,
)
def create_project_api_key(
    project_ref: str,
    body: CreateProjectApiKeyRequest,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> CreatedProjectApiKeyRead:
    """Create a project API key. Plaintext is returned exactly once."""
    project = _resolve_project(db, auth, project_ref)
    try:
        created = user_api_key_service.create_project_api_key(
            db, project=project, name=body.name, scopes=body.scopes
        )
    except ApiKeyValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(created.api_key)
    return CreatedProjectApiKeyRead(
        key=ProjectApiKeyMetadataRead.model_validate(created.api_key),
        plaintext_key=created.token,
    )


@router.post(
    "/projects/{project_ref}/api-keys/{key_id}/revoke",
    response_model=ProjectApiKeyMetadataRead,
)
def revoke_project_api_key(
    project_ref: str,
    key_id: uuid.UUID,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> ProjectApiKeyMetadataRead:
    """Revoke a project API key (idempotent). Historical row is retained."""
    project = _resolve_project(db, auth, project_ref)
    api_key = user_api_key_service.get_project_api_key(
        db, project=project, key_id=key_id
    )
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")
    revoked = user_api_key_service.revoke_project_api_key(db, api_key=api_key)
    db.commit()
    db.refresh(revoked)
    return ProjectApiKeyMetadataRead.model_validate(revoked)


def _require_organization(db: Session, auth: HumanAuthContext) -> Organization:
    org = db.get(Organization, uuid.UUID(auth.local_org_id))
    if org is None:
        # Should be unreachable after require_org_member; keep fail-closed.
        raise HTTPException(status_code=403, detail="organization is not linked")
    return org


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


@router.post(
    "/projects/{project_ref}/analysis",
    response_model=ProjectAnalysisRead,
)
async def analyze_project(
    project_ref: str,
    request: ProjectAnalysisRequest | None = None,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> ProjectAnalysisRead:
    """Run the deterministic project-window evidence analysis.

    Compares the selected current window against the immediately preceding
    equal-length baseline window over canonical OTel data for one authorized
    project. Ephemeral, content-excluding, and bounded: nothing is persisted,
    and callers cannot override project, ``as_of``, thresholds, provider, or
    model — only ``hours``, an optional rule-ID subset, and the optional
    narrative flag.
    """
    project = _resolve_project(db, auth, project_ref)
    hours = request.hours if request is not None else 24
    rules = request.rules if request is not None else None
    include_narrative = bool(request.include_narrative) if request is not None else False
    try:
        return await project_analysis_service.analyze_project(
            db,
            project=project,
            hours=hours,
            rules=rules,
            include_narrative=include_narrative,
        )
    except AnalystValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post(
    "/projects/{project_ref}/analysis/traces/{trace_id}",
    response_model=TraceAnalysisRead,
)
async def analyze_project_trace(
    project_ref: str,
    trace_id: str,
    request: TraceAnalysisRequest | None = None,
    auth: HumanAuthContext = Depends(require_org_member),
    db: Session = Depends(get_db),
) -> TraceAnalysisRead:
    """Run the deterministic evidence engine on one project-scoped trace.

    Ephemeral and content-excluding: nothing is persisted. Deterministic
    findings are always computed first. When ``include_narrative`` is true and
    the environment is configured for it, an optional provider may explain
    existing evidence IDs; provider failure never suppresses deterministic
    results. Callers cannot override project, trace, ruleset, provider, or
    model — only an optional rule-ID subset and the narrative flag.
    """
    project = _resolve_project(db, auth, project_ref)
    rules = request.rules if request is not None else None
    include_narrative = bool(request.include_narrative) if request is not None else False
    try:
        analysis = await trace_analysis_service.analyze_project_trace(
            db,
            project=project,
            trace_id=trace_id,
            rules=rules,
            include_narrative=include_narrative,
        )
    except AnalystValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if analysis is None:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return analysis
