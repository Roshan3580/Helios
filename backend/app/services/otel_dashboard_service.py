"""Project-scoped dashboard aggregates over canonical OTel tables.

All filters bind project_id and a start_time window. Span-level metrics join
through otel_traces so the window is always evaluated on trace start_time.
Token and model values come only from documented GenAI attributes; missing or
malformed values are ignored, never estimated.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Float, and_, cast, case, func, or_, select
from sqlalchemy.orm import Session

from app.models import Project
from app.models_otel import STATUS_CODE_ERROR, OtelSpan, OtelTrace
from app.otel_genai_attributes import (
    INPUT_TOKEN_KEYS,
    OUTPUT_TOKEN_KEYS,
    REQUEST_MODEL_KEY,
    RESPONSE_MODEL_KEY,
)

RECENT_ERRORS_LIMIT = 10


def _jsonb_number(attributes_col, key: str):
    """Read a JSONB number; non-numeric / missing → NULL (safe for SUM)."""
    elem = attributes_col[key]
    return case(
        (func.jsonb_typeof(elem) == "number", cast(elem.as_string(), Float)),
        else_=None,
    )


def _jsonb_string(attributes_col, key: str):
    elem = attributes_col[key]
    return case(
        (func.jsonb_typeof(elem) == "string", elem.as_string()),
        else_=None,
    )


def _coalesce_numbers(attributes_col, keys: tuple[str, ...]):
    return func.coalesce(*[_jsonb_number(attributes_col, key) for key in keys])


def _model_expr(attributes_col):
    """Prefer gen_ai.request.model, fall back to gen_ai.response.model."""
    return func.coalesce(
        _jsonb_string(attributes_col, REQUEST_MODEL_KEY),
        _jsonb_string(attributes_col, RESPONSE_MODEL_KEY),
    )


def _trace_duration_ms():
    return func.extract("epoch", OtelTrace.end_time - OtelTrace.start_time) * 1000.0


def _span_duration_ms():
    return cast(OtelSpan.duration_ns, Float) / 1_000_000.0


def _round_ms(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _error_rate(errors: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(errors / total, 6)


def get_project_dashboard(
    db: Session,
    *,
    project: Project,
    hours: int = 24,
    now: datetime | None = None,
) -> dict:
    if hours < 1 or hours > 720:
        raise ValueError("hours must be between 1 and 720")

    window_end = now or datetime.now(timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    window_start = window_end - timedelta(hours=hours)
    project_id: uuid.UUID = project.id

    trace_filter = and_(
        OtelTrace.project_id == project_id,
        OtelTrace.start_time >= window_start,
        OtelTrace.start_time <= window_end,
    )
    duration_ms = _trace_duration_ms()

    overview_row = db.execute(
        select(
            func.count().label("trace_count"),
            func.coalesce(
                func.sum(case((OtelTrace.error_count > 0, 1), else_=0)), 0
            ).label("error_trace_count"),
            func.coalesce(func.sum(OtelTrace.span_count), 0).label("total_span_count"),
            func.avg(duration_ms).label("avg_duration_ms"),
            func.percentile_cont(0.5).within_group(duration_ms).label("p50_duration_ms"),
            func.percentile_cont(0.95).within_group(duration_ms).label("p95_duration_ms"),
            func.count(func.distinct(OtelTrace.service_name)).label(
                "distinct_service_count"
            ),
        ).where(trace_filter)
    ).one()

    trace_count = int(overview_row.trace_count or 0)
    error_trace_count = int(overview_row.error_trace_count or 0)
    overview = {
        "trace_count": trace_count,
        "error_trace_count": error_trace_count,
        "trace_error_rate": _error_rate(error_trace_count, trace_count),
        "total_span_count": int(overview_row.total_span_count or 0),
        "avg_duration_ms": _round_ms(overview_row.avg_duration_ms)
        if trace_count
        else None,
        "p50_duration_ms": _round_ms(overview_row.p50_duration_ms)
        if trace_count
        else None,
        "p95_duration_ms": _round_ms(overview_row.p95_duration_ms)
        if trace_count
        else None,
        "distinct_service_count": int(overview_row.distinct_service_count or 0)
        if trace_count
        else 0,
    }

    services = _service_breakdown(db, trace_filter=trace_filter, duration_ms=duration_ms)
    tokens, models = _token_and_model_breakdown(
        db, project_id=project_id, window_start=window_start, window_end=window_end
    )
    recent_errors = _recent_errors(db, trace_filter=trace_filter, duration_ms=duration_ms)
    latency_trend = _latency_trend(
        db,
        trace_filter=trace_filter,
        duration_ms=duration_ms,
        hours=hours,
    )

    return {
        "project_id": project.id,
        "project_slug": project.slug,
        "hours": hours,
        "window_start": window_start,
        "window_end": window_end,
        "overview": overview,
        "tokens": tokens,
        "services": services,
        "models": models,
        "recent_errors": recent_errors,
        "latency_trend": latency_trend,
    }


def _service_breakdown(db: Session, *, trace_filter, duration_ms) -> list[dict]:
    rows = db.execute(
        select(
            OtelTrace.service_name,
            func.count().label("trace_count"),
            func.coalesce(
                func.sum(case((OtelTrace.error_count > 0, 1), else_=0)), 0
            ).label("error_trace_count"),
            func.avg(duration_ms).label("avg_duration_ms"),
            func.percentile_cont(0.5).within_group(duration_ms).label("p50_duration_ms"),
            func.percentile_cont(0.95).within_group(duration_ms).label("p95_duration_ms"),
            func.coalesce(func.sum(OtelTrace.span_count), 0).label("total_spans"),
        )
        .where(trace_filter)
        .group_by(OtelTrace.service_name)
        .order_by(OtelTrace.service_name.asc())
    ).all()

    result: list[dict] = []
    for row in rows:
        tc = int(row.trace_count or 0)
        ec = int(row.error_trace_count or 0)
        result.append(
            {
                "service_name": row.service_name,
                "trace_count": tc,
                "error_trace_count": ec,
                "error_rate": _error_rate(ec, tc),
                "avg_duration_ms": _round_ms(row.avg_duration_ms),
                "p50_duration_ms": _round_ms(row.p50_duration_ms),
                "p95_duration_ms": _round_ms(row.p95_duration_ms),
                "total_spans": int(row.total_spans or 0),
            }
        )
    return result


def _token_and_model_breakdown(
    db: Session,
    *,
    project_id: uuid.UUID,
    window_start: datetime,
    window_end: datetime,
) -> tuple[dict, list[dict]]:
    attrs = OtelSpan.attributes
    input_expr = _coalesce_numbers(attrs, INPUT_TOKEN_KEYS)
    output_expr = _coalesce_numbers(attrs, OUTPUT_TOKEN_KEYS)
    model_expr = _model_expr(attrs)
    span_ms = _span_duration_ms()

    span_filter = and_(
        OtelSpan.project_id == project_id,
        OtelTrace.project_id == project_id,
        OtelTrace.start_time >= window_start,
        OtelTrace.start_time <= window_end,
    )

    token_row = db.execute(
        select(
            func.coalesce(func.sum(input_expr), 0).label("input_tokens"),
            func.coalesce(func.sum(output_expr), 0).label("output_tokens"),
            func.coalesce(
                func.sum(
                    case(
                        (or_(input_expr.is_not(None), output_expr.is_not(None)), 1),
                        else_=0,
                    )
                ),
                0,
            ).label("spans_with_token_data"),
        )
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(span_filter)
    ).one()

    input_tokens = int(token_row.input_tokens or 0)
    output_tokens = int(token_row.output_tokens or 0)
    tokens = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "spans_with_token_data": int(token_row.spans_with_token_data or 0),
    }

    model_rows = db.execute(
        select(
            model_expr.label("model"),
            func.count().label("span_count"),
            func.count(func.distinct(OtelSpan.trace_id)).label("trace_count"),
            func.coalesce(func.sum(input_expr), 0).label("input_tokens"),
            func.coalesce(func.sum(output_expr), 0).label("output_tokens"),
            func.coalesce(
                func.sum(case((OtelSpan.status_code == STATUS_CODE_ERROR, 1), else_=0)),
                0,
            ).label("error_span_count"),
            func.avg(span_ms).label("avg_duration_ms"),
        )
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(and_(span_filter, model_expr.is_not(None)))
        .group_by(model_expr)
        .order_by(model_expr.asc())
    ).all()

    models = [
        {
            "model": row.model,
            "span_count": int(row.span_count or 0),
            "trace_count": int(row.trace_count or 0),
            "input_tokens": int(row.input_tokens or 0),
            "output_tokens": int(row.output_tokens or 0),
            "error_span_count": int(row.error_span_count or 0),
            "avg_duration_ms": _round_ms(row.avg_duration_ms),
        }
        for row in model_rows
    ]
    return tokens, models


def _recent_errors(db: Session, *, trace_filter, duration_ms) -> list[dict]:
    rows = db.execute(
        select(
            OtelTrace.trace_id,
            OtelTrace.service_name,
            OtelTrace.root_span_name,
            OtelTrace.start_time,
            duration_ms.label("duration_ms"),
            OtelTrace.span_count,
            OtelTrace.error_count,
        )
        .where(and_(trace_filter, OtelTrace.error_count > 0))
        .order_by(OtelTrace.start_time.desc())
        .limit(RECENT_ERRORS_LIMIT)
    ).all()

    return [
        {
            "trace_id": row.trace_id,
            "service_name": row.service_name,
            "root_span_name": row.root_span_name,
            "start_time": row.start_time,
            "duration_ms": _round_ms(row.duration_ms) or 0.0,
            "span_count": int(row.span_count or 0),
            "error_count": int(row.error_count or 0),
        }
        for row in rows
    ]


def _latency_trend(
    db: Session, *, trace_filter, duration_ms, hours: int
) -> list[dict]:
    trunc_unit = "hour" if hours <= 24 else "day"
    bucket = func.date_trunc(trunc_unit, OtelTrace.start_time)

    rows = db.execute(
        select(
            bucket.label("bucket_start"),
            func.count().label("trace_count"),
            func.coalesce(
                func.sum(case((OtelTrace.error_count > 0, 1), else_=0)), 0
            ).label("error_count"),
            func.avg(duration_ms).label("avg_duration_ms"),
            func.percentile_cont(0.95).within_group(duration_ms).label("p95_duration_ms"),
        )
        .where(trace_filter)
        .group_by(bucket)
        .order_by(bucket.asc())
    ).all()

    return [
        {
            "bucket_start": row.bucket_start,
            "trace_count": int(row.trace_count or 0),
            "error_count": int(row.error_count or 0),
            "avg_duration_ms": _round_ms(row.avg_duration_ms),
            "p95_duration_ms": _round_ms(row.p95_duration_ms),
        }
        for row in rows
    ]
