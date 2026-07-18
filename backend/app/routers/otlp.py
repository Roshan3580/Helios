"""Canonical v2 OTLP/HTTP ingestion endpoint.

POST /v1/otlp/traces
- protobuf only (Content-Type: application/x-protobuf); no JSON multiplexing
- project identified by the temporary X-Helios-Project-Slug header until
  API-key authentication replaces it (see ADR 001)
- full-batch transactional semantics: the whole export succeeds or fails;
  partial acceptance is never claimed
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.database import get_db
from app.otlp.parser import OtlpDecodeError, OtlpValidationError, parse_export_request
from app.services import otel_ingest_service
from app.services.project_service import get_or_create_project

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
MAX_PROJECT_SLUG_LENGTH = 128


def _protobuf_success() -> Response:
    return Response(
        content=ExportTraceServiceResponse().SerializeToString(),
        media_type=PROTOBUF_CONTENT_TYPE,
        status_code=200,
    )


@router.post("/traces")
async def ingest_otlp_traces(
    request: Request,
    db: Session = Depends(get_db),
) -> Response:
    """Read the raw body before any framework content parsing, then hand off
    to the synchronous ingest path in a worker thread."""
    payload = await request.body()
    return await run_in_threadpool(
        _ingest_sync,
        payload,
        request.headers.get("content-type"),
        request.headers.get("x-helios-project-slug"),
        request.headers.get("x-helios-environment"),
        db,
    )


def _ingest_sync(
    payload: bytes,
    content_type: str | None,
    x_helios_project_slug: str | None,
    x_helios_environment: str | None,
    db: Session,
) -> Response:
    if not content_type or not content_type.split(";")[0].strip() == PROTOBUF_CONTENT_TYPE:
        logger.warning("otlp reject: unsupported content type %r", content_type)
        raise HTTPException(
            status_code=415,
            detail=f"unsupported content type; use {PROTOBUF_CONTENT_TYPE}",
        )

    project_slug = (x_helios_project_slug or "").strip()
    if not project_slug or len(project_slug) > MAX_PROJECT_SLUG_LENGTH:
        logger.warning("otlp reject: missing or invalid project slug")
        raise HTTPException(
            status_code=400,
            detail="X-Helios-Project-Slug header is required and must be a valid slug",
        )

    if not payload:
        logger.warning("otlp reject: empty body (project=%s)", project_slug)
        raise HTTPException(status_code=400, detail="request body is empty")

    if len(payload) > MAX_REQUEST_BODY_BYTES:
        logger.warning(
            "otlp reject: body too large (%d bytes, project=%s)", len(payload), project_slug
        )
        raise HTTPException(
            status_code=413,
            detail=f"request body exceeds {MAX_REQUEST_BODY_BYTES} bytes",
        )

    try:
        spans = parse_export_request(payload)
    except OtlpDecodeError:
        logger.warning("otlp reject: malformed protobuf (project=%s)", project_slug)
        raise HTTPException(status_code=400, detail="malformed OTLP protobuf payload")
    except OtlpValidationError as exc:
        # Message is Helios-generated (ID format details only), safe to return.
        logger.warning("otlp reject: invalid span data (project=%s): %s", project_slug, exc)
        raise HTTPException(status_code=400, detail=f"invalid OTLP span data: {exc}")

    environment = (x_helios_environment or "").strip() or None

    try:
        project = get_or_create_project(db, slug=project_slug)
        result = otel_ingest_service.ingest_spans(
            db, project, spans, environment_fallback=environment
        )
        db.commit()
    except Exception:
        db.rollback()
        # Never leak SQLAlchemy/psycopg/protobuf internals to clients.
        logger.exception(
            "otlp ingestion failed (project=%s, spans=%d)", project_slug, len(spans)
        )
        raise HTTPException(status_code=500, detail="trace ingestion failed")

    logger.info(
        "otlp ingest ok (project=%s, traces=%d, spans=%d)",
        project_slug,
        result["traces"],
        result["spans"],
    )
    return _protobuf_success()
