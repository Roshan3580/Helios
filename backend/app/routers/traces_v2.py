"""Canonical v2 read APIs over the OTel trace store.

Requires Authorization: Bearer <project-api-key> with the traces:read scope.
The project is derived exclusively from the authenticated key; there is no
project_slug parameter, so a caller cannot read another project's traces.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas_v2 import OtelTraceDetailRead, OtelTraceSummaryRead
from app.security.api_keys import SCOPE_TRACES_READ, AuthContext
from app.security.dependencies import require_scope
from app.services import otel_trace_service

router = APIRouter(prefix="/traces", tags=["traces-v2"])


@router.get("", response_model=list[OtelTraceSummaryRead])
def list_traces_v2(
    limit: int = Query(default=50, ge=1, le=200),
    service_name: str | None = Query(default=None),
    has_errors: bool | None = Query(default=None),
    auth: AuthContext = Depends(require_scope(SCOPE_TRACES_READ)),
    db: Session = Depends(get_db),
) -> list[dict]:
    return otel_trace_service.list_traces(
        db,
        project_slug=auth.project_slug,
        limit=limit,
        service_name=service_name,
        has_errors=has_errors,
    )


@router.get("/{trace_id}", response_model=OtelTraceDetailRead)
def get_trace_v2(
    trace_id: str,
    auth: AuthContext = Depends(require_scope(SCOPE_TRACES_READ)),
    db: Session = Depends(get_db),
) -> dict:
    detail = otel_trace_service.get_trace_detail(
        db, project_slug=auth.project_slug, trace_id=trace_id
    )
    if not detail:
        # Traces in other projects are indistinguishable from missing ones.
        raise HTTPException(
            status_code=404,
            detail=f"Trace '{trace_id}' not found",
        )
    return detail
