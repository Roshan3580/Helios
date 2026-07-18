"""Canonical v2 read APIs over the OTel trace store.

project_slug is a required query parameter: unscoped reads are impossible.
This explicit parameter is temporary until project-scoped API keys resolve
the project from credentials (see ADR 001).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas_v2 import OtelTraceDetailRead, OtelTraceSummaryRead
from app.services import otel_trace_service

router = APIRouter(prefix="/traces", tags=["traces-v2"])


@router.get("", response_model=list[OtelTraceSummaryRead])
def list_traces_v2(
    project_slug: str = Query(min_length=1, max_length=128),
    limit: int = Query(default=50, ge=1, le=200),
    service_name: str | None = Query(default=None),
    has_errors: bool | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[dict]:
    return otel_trace_service.list_traces(
        db,
        project_slug=project_slug,
        limit=limit,
        service_name=service_name,
        has_errors=has_errors,
    )


@router.get("/{trace_id}", response_model=OtelTraceDetailRead)
def get_trace_v2(
    trace_id: str,
    project_slug: str = Query(min_length=1, max_length=128),
    db: Session = Depends(get_db),
) -> dict:
    detail = otel_trace_service.get_trace_detail(
        db, project_slug=project_slug, trace_id=trace_id
    )
    if not detail:
        raise HTTPException(
            status_code=404,
            detail=f"Trace '{trace_id}' not found in project '{project_slug}'",
        )
    return detail
