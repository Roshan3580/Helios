"""Canonical v2 OTLP/HTTP ingestion endpoint.

POST /v1/otlp/traces
- protobuf only (Content-Type: application/x-protobuf); no JSON multiplexing
- requires Authorization: Bearer <project-api-key> with the traces:ingest
  scope; the project is derived solely from the authenticated key (see ADR 002)
- full-batch transactional semantics: the whole export succeeds or fails;
  partial acceptance is never claimed
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.models import Project
from app.otlp.parser import OtlpDecodeError, OtlpValidationError, parse_export_request
from app.security.api_keys import SCOPE_TRACES_INGEST, AuthContext
from app.security.dependencies import require_scope
from app.services import otel_ingest_service

try:  # generated protobuf response class
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
        ExportTraceServiceResponse,
    )
except ImportError as exc:  # pragma: no cover - hard dependency
    raise RuntimeError("opentelemetry-proto is required for OTLP ingestion") from exc

logger = logging.getLogger("helios.otlp")

router = APIRouter(prefix="/otlp", tags=["otlp"])

PROTOBUF_CONTENT_TYPE = "application/x-protobuf"
MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024  # 4 MiB application-level limit


def _protobuf_success() -> Response:
    return Response(
        content=ExportTraceServiceResponse().SerializeToString(),
        media_type=PROTOBUF_CONTENT_TYPE,
        status_code=200,
    )


@router.post("/traces")
async def ingest_otlp_traces(
    request: Request,
    auth: AuthContext = Depends(require_scope(SCOPE_TRACES_INGEST)),
    db: Session = Depends(get_db),
) -> Response:
    """Read the raw body before any framework content parsing, then hand off
    to the synchronous ingest path in a worker thread. The project comes only
    from the authenticated key."""
    payload = await request.body()
    return await run_in_threadpool(
        _ingest_sync,
        payload,
        request.headers.get("content-type"),
        request.headers.get("x-helios-environment"),
        auth,
        db,
    )


def _ingest_sync(
    payload: bytes,
    content_type: str | None,
    x_helios_environment: str | None,
    auth: AuthContext,
    db: Session,
) -> Response:
    if not content_type or not content_type.split(";")[0].strip() == PROTOBUF_CONTENT_TYPE:
        logger.warning("otlp reject: unsupported content type %r", content_type)
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content type; use {PROTOBUF_CONTENT_TYPE}",
        )

    if not payload:
        logger.warning("otlp reject: empty body (project=%s)", auth.project_slug)
        raise HTTPException(status_code=400, detail="request body is empty")

    if len(payload) > MAX_REQUEST_BODY_BYTES:
        logger.warning(
            "otlp reject: body too large (%d bytes, project=%s)",
            len(payload),
            auth.project_slug,
        )
        raise HTTPException(
            status_code=413,
            detail=f"request body exceeds {MAX_REQUEST_BODY_BYTES} bytes",
        )

    try:
        spans = parse_export_request(payload)
    except OtlpDecodeError:
        logger.warning("otlp reject: malformed protobuf (project=%s)", auth.project_slug)
        raise HTTPException(status_code=400, detail="malformed OTLP protobuf payload")
    except OtlpValidationError as exc:
        # Message is Helios-generated (ID format details only), safe to return.
        logger.warning(
            "otlp reject: invalid span data (project=%s): %s", auth.project_slug, exc
        )
        raise HTTPException(status_code=400, detail=f"invalid OTLP span data: {exc}")

    environment = (x_helios_environment or "").strip() or None

    try:
        # A valid key always belongs to an existing project; no creation here.
        project = db.get(Project, uuid.UUID(auth.project_id))
        if project is None:  # pragma: no cover - key FK guarantees presence
            raise HTTPException(status_code=401, detail="invalid authentication credentials")
        result = otel_ingest_service.ingest_spans(
            db, project, spans, environment_fallback=environment
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        # Never leak SQLAlchemy/psycopg/protobuf internals to clients.
        logger.exception(
            "otlp ingestion failed (project=%s, spans=%d)", auth.project_slug, len(spans)
        )
        raise HTTPException(status_code=500, detail="trace ingestion failed")

    logger.info(
        "otlp ingest ok (project=%s, traces=%d, spans=%d)",
        auth.project_slug,
        result["traces"],
        result["spans"],
    )
    return _protobuf_success()
