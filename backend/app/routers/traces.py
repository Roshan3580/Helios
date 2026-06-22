from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import TraceCreate, TraceDetailRead, TraceRead
from app.services import trace_service

router = APIRouter(prefix="/traces", tags=["traces"])


@router.get("", response_model=list[TraceRead])
def get_traces(
    project_slug: str | None = Query(default=None),
    status: str | None = Query(default=None),
    model: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[TraceRead]:
    return trace_service.list_traces(
        db,
        project_slug=project_slug,
        status=status,
        model=model,
        limit=limit,
    )


@router.get("/{trace_id}", response_model=TraceDetailRead)
def get_trace(trace_id: str, db: Session = Depends(get_db)) -> TraceDetailRead:
    trace = trace_service.get_trace_detail(db, trace_id)
    if not trace:
        raise HTTPException(status_code=404, detail=f"Trace '{trace_id}' not found")
    return trace


@router.post("", response_model=TraceDetailRead, status_code=201)
def ingest_trace(payload: TraceCreate, db: Session = Depends(get_db)) -> TraceDetailRead:
    try:
        trace = trace_service.create_trace(db, payload)
        db.commit()
        return trace
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
