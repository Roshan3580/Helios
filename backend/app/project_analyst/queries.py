"""Bounded SQL evidence collection for project-window analysis.

Every query binds ``project_id`` and the exact half-open window boundaries
(``start_time >= start AND start_time < end`` on the trace). Span-level
queries always join through ``otel_traces`` so window membership is evaluated
on trace start time. Aggregates (counts, rates, percentiles) cover all
matching rows; only example traces, per-entity breakdowns, and the error-span
candidate set are capped, with truncation reported back to the caller.

Token and model values come exclusively from documented GenAI attributes read
as JSONB; malformed (non-numeric / non-string) values are ignored, never
estimated. No content-bearing attribute (prompt, completion, tool arguments,
events, documents) is ever selected.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Sequence

from sqlalchemy import Float, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

from app.models_otel import STATUS_CODE_ERROR, OtelSpan, OtelTrace
from app.otel_genai_attributes import (
    INPUT_TOKEN_KEYS,
    OUTPUT_TOKEN_KEYS,
    REQUEST_MODEL_KEY,
    RESPONSE_MODEL_KEY,
)
from app.project_analyst.evidence import (
    normalize_exception_type,
    normalize_status_message,
    signature_label,
    trace_ui_path,
)
from app.project_analyst.models import (
    ErrorClusterStats,
    GenAiGapStats,
    ModelWindowStats,
    ProjectCoverage,
    ProjectWindow,
    ProjectWindowEvidence,
    ServiceWindowStats,
    SupportingTraceRef,
    WindowAggregate,
)
from app.project_analyst.thresholds import (
    ERROR_RATE_MIN_TRACES_PER_WINDOW,
    MAX_ERROR_GROUPS,
    MAX_ERROR_SPAN_CANDIDATES,
    MAX_EXAMPLE_TRACES_PER_FINDING,
    MAX_MODELS_ANALYZED,
    MAX_SERVICES_ANALYZED,
    MAX_SUPPORTING_SPAN_IDS,
    OUTLIER_MIN_DURATION_MS,
    OUTLIER_P95_FACTOR,
)

# Classification attribute keys (same contract as the single-trace engine).
_HELIOS_SPAN_TYPE = "helios.span.type"
_TOOL_NAME = "tool.name"
_GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
_EXCEPTION_TYPE = "exception.type"
# Official OpenAI instrumentation scope prefix (see ADR 003 / SDK).
_OPENAI_SCOPE_PREFIX = "opentelemetry.instrumentation.openai"

# Raw status-message bound applied in SQL before Python normalization.
_SQL_STATUS_MESSAGE_BOUND = 256


def _jsonb_number(attributes_col, key: str):
    """Read a JSONB number; non-numeric / missing -> NULL (never estimated)."""
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
    """Canonical precedence: gen_ai.request.model, then gen_ai.response.model."""
    return func.coalesce(
        _jsonb_string(attributes_col, REQUEST_MODEL_KEY),
        _jsonb_string(attributes_col, RESPONSE_MODEL_KEY),
    )


def _trace_duration_ms():
    return func.extract("epoch", OtelTrace.end_time - OtelTrace.start_time) * 1000.0


def _span_duration_ms():
    return cast(OtelSpan.duration_ns, Float) / 1_000_000.0


def _round_ms(value) -> float | None:
    if value is None:
        return None
    return round(float(value), 3)


def _trace_window_filter(project_id: uuid.UUID, window: ProjectWindow):
    return and_(
        OtelTrace.project_id == project_id,
        OtelTrace.start_time >= window.start,
        OtelTrace.start_time < window.end,
    )


def _span_window_filter(project_id: uuid.UUID, window: ProjectWindow):
    """Span membership through the project-scoped traces in the window."""
    return and_(
        OtelSpan.project_id == project_id,
        _trace_window_filter(project_id, window),
    )


def _model_like_expr(attrs):
    return or_(
        _jsonb_string(attrs, _HELIOS_SPAN_TYPE) == "llm",
        _model_expr(attrs).is_not(None),
        _jsonb_string(attrs, _GEN_AI_OPERATION_NAME).is_not(None),
    )


def _tool_like_expr(attrs):
    return or_(
        _jsonb_string(attrs, _HELIOS_SPAN_TYPE) == "tool",
        _jsonb_string(attrs, _TOOL_NAME).is_not(None),
    )


def _explicitly_classified_expr(attrs):
    return or_(
        _jsonb_string(attrs, _HELIOS_SPAN_TYPE) == "llm",
        OtelSpan.scope_name.like(f"{_OPENAI_SCOPE_PREFIX}%"),
    )


def _count_if(condition) -> object:
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


def _trace_ref_columns(duration_ms):
    return (
        OtelTrace.trace_id,
        OtelTrace.service_name,
        OtelTrace.root_span_name,
        OtelTrace.start_time,
        duration_ms.label("duration_ms"),
        OtelTrace.span_count,
        OtelTrace.error_count,
    )


def _row_to_ref(row) -> SupportingTraceRef:
    return SupportingTraceRef(
        trace_id=row.trace_id,
        service_name=row.service_name,
        root_span_name=row.root_span_name,
        start_time=row.start_time,
        duration_ms=_round_ms(row.duration_ms) or 0.0,
        span_count=int(row.span_count or 0),
        error_count=int(row.error_count or 0),
        trace_ui_path=trace_ui_path(row.trace_id),
    )


def _window_aggregate(
    db: Session, *, project_id: uuid.UUID, window: ProjectWindow
) -> WindowAggregate:
    duration_ms = _trace_duration_ms()
    row = db.execute(
        select(
            func.count().label("trace_count"),
            _count_if(OtelTrace.error_count > 0).label("error_trace_count"),
            func.percentile_cont(0.5).within_group(duration_ms).label("p50"),
            func.percentile_cont(0.95).within_group(duration_ms).label("p95"),
        ).where(_trace_window_filter(project_id, window))
    ).one()
    span_count = db.scalar(
        select(func.count())
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(_span_window_filter(project_id, window))
    )
    trace_count = int(row.trace_count or 0)
    return WindowAggregate(
        trace_count=trace_count,
        error_trace_count=int(row.error_trace_count or 0),
        span_count=int(span_count or 0),
        p50_duration_ms=_round_ms(row.p50) if trace_count else None,
        p95_duration_ms=_round_ms(row.p95) if trace_count else None,
    )


def _service_stats(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    limit: int | None,
    only_services: Sequence[str] | None = None,
) -> list[ServiceWindowStats]:
    duration_ms = _trace_duration_ms()
    stmt = (
        select(
            OtelTrace.service_name,
            func.count().label("trace_count"),
            _count_if(OtelTrace.error_count > 0).label("error_trace_count"),
            func.percentile_cont(0.5).within_group(duration_ms).label("p50"),
            func.percentile_cont(0.95).within_group(duration_ms).label("p95"),
        )
        .where(_trace_window_filter(project_id, window))
        .group_by(OtelTrace.service_name)
        .order_by(func.count().desc(), OtelTrace.service_name.asc())
    )
    if only_services is not None:
        if not only_services:
            return []
        stmt = stmt.where(OtelTrace.service_name.in_(list(only_services)))
    if limit is not None:
        stmt = stmt.limit(limit)
    return [
        ServiceWindowStats(
            service_name=row.service_name,
            trace_count=int(row.trace_count or 0),
            error_trace_count=int(row.error_trace_count or 0),
            p50_duration_ms=_round_ms(row.p50),
            p95_duration_ms=_round_ms(row.p95),
        )
        for row in db.execute(stmt).all()
    ]


def _model_stats(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    limit: int | None,
    only_models: Sequence[str] | None = None,
) -> list[ModelWindowStats]:
    attrs = OtelSpan.attributes
    model = _model_expr(attrs)
    span_ms = _span_duration_ms()
    input_expr = _coalesce_numbers(attrs, INPUT_TOKEN_KEYS)
    output_expr = _coalesce_numbers(attrs, OUTPUT_TOKEN_KEYS)
    has_tokens = or_(input_expr.is_not(None), output_expr.is_not(None))
    total_expr = case(
        (
            has_tokens,
            func.coalesce(input_expr, 0.0) + func.coalesce(output_expr, 0.0),
        ),
        else_=None,
    )
    stmt = (
        select(
            model.label("model"),
            func.count().label("span_count"),
            func.percentile_cont(0.5).within_group(span_ms).label("p50"),
            func.percentile_cont(0.95).within_group(span_ms).label("p95"),
            _count_if(has_tokens).label("token_span_count"),
            func.coalesce(func.sum(input_expr), 0).label("input_tokens"),
            func.coalesce(func.sum(output_expr), 0).label("output_tokens"),
            func.coalesce(func.sum(total_expr), 0).label("total_tokens"),
        )
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(and_(_span_window_filter(project_id, window), model.is_not(None)))
        .group_by(model)
        .order_by(func.count().desc(), model.asc())
    )
    if only_models is not None:
        if not only_models:
            return []
        stmt = stmt.where(model.in_(list(only_models)))
    if limit is not None:
        stmt = stmt.limit(limit)
    return [
        ModelWindowStats(
            model=row.model,
            span_count=int(row.span_count or 0),
            p50_duration_ms=_round_ms(row.p50),
            p95_duration_ms=_round_ms(row.p95),
            token_span_count=int(row.token_span_count or 0),
            input_tokens=float(row.input_tokens or 0),
            output_tokens=float(row.output_tokens or 0),
            total_tokens=float(row.total_tokens or 0),
        )
        for row in db.execute(stmt).all()
    ]


def _trace_examples_by_service(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    services: Sequence[str],
    errors_only: bool,
    order_by_duration: bool,
) -> dict[str, list[SupportingTraceRef]]:
    """Bounded per-service examples via one window-function query (no N+1)."""
    if not services:
        return {}
    duration_ms = _trace_duration_ms()
    if order_by_duration:
        ordering = (duration_ms.desc(), OtelTrace.trace_id.asc())
    else:
        ordering = (OtelTrace.start_time.desc(), OtelTrace.trace_id.asc())
    rn = (
        func.row_number()
        .over(partition_by=OtelTrace.service_name, order_by=ordering)
        .label("rn")
    )
    conditions = [
        _trace_window_filter(project_id, window),
        OtelTrace.service_name.in_(list(services)),
    ]
    if errors_only:
        conditions.append(OtelTrace.error_count > 0)
    sub = (
        select(*_trace_ref_columns(duration_ms), rn).where(and_(*conditions))
    ).subquery()
    rows = db.execute(
        select(sub)
        .where(sub.c.rn <= MAX_EXAMPLE_TRACES_PER_FINDING)
        .order_by(sub.c.service_name.asc(), sub.c.rn.asc())
    ).all()
    out: dict[str, list[SupportingTraceRef]] = {}
    for row in rows:
        out.setdefault(row.service_name, []).append(_row_to_ref(row))
    return out


def _trace_examples_by_model(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    models: Sequence[str],
    by_tokens: bool,
) -> dict[str, list[SupportingTraceRef]]:
    """Traces containing the slowest / highest-token spans per model."""
    if not models:
        return {}
    attrs = OtelSpan.attributes
    model = _model_expr(attrs)
    span_ms = _span_duration_ms()
    input_expr = _coalesce_numbers(attrs, INPUT_TOKEN_KEYS)
    output_expr = _coalesce_numbers(attrs, OUTPUT_TOKEN_KEYS)
    has_tokens = or_(input_expr.is_not(None), output_expr.is_not(None))
    total_expr = func.coalesce(input_expr, 0.0) + func.coalesce(output_expr, 0.0)
    metric = total_expr if by_tokens else span_ms
    rn = (
        func.row_number()
        .over(partition_by=model, order_by=(metric.desc(), OtelSpan.span_id.asc()))
        .label("rn")
    )
    duration_ms = _trace_duration_ms()
    conditions = [
        _span_window_filter(project_id, window),
        model.is_not(None),
        model.in_(list(models)),
    ]
    if by_tokens:
        conditions.append(has_tokens)
    sub = (
        select(model.label("model"), *_trace_ref_columns(duration_ms), rn)
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(and_(*conditions))
    ).subquery()
    # Fetch extra rows per model: duplicates (several qualifying spans in the
    # same trace) are removed below while preserving deterministic order.
    rows = db.execute(
        select(sub)
        .where(sub.c.rn <= MAX_EXAMPLE_TRACES_PER_FINDING * 3)
        .order_by(sub.c.model.asc(), sub.c.rn.asc())
    ).all()
    out: dict[str, list[SupportingTraceRef]] = {}
    for row in rows:
        refs = out.setdefault(row.model, [])
        if len(refs) >= MAX_EXAMPLE_TRACES_PER_FINDING:
            continue
        if any(ref.trace_id == row.trace_id for ref in refs):
            continue
        refs.append(_row_to_ref(row))
    return out


def _outliers(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    current_p95_ms: float | None,
) -> tuple[int, list[SupportingTraceRef]]:
    if current_p95_ms is None or current_p95_ms <= 0:
        return 0, []
    threshold_ms = max(OUTLIER_P95_FACTOR * current_p95_ms, OUTLIER_MIN_DURATION_MS)
    duration_ms = _trace_duration_ms()
    condition = and_(
        _trace_window_filter(project_id, window), duration_ms >= threshold_ms
    )
    count = int(db.scalar(select(func.count()).where(condition)) or 0)
    if count == 0:
        return 0, []
    rows = db.execute(
        select(*_trace_ref_columns(duration_ms))
        .where(condition)
        .order_by(duration_ms.desc(), OtelTrace.trace_id.asc())
        .limit(MAX_EXAMPLE_TRACES_PER_FINDING)
    ).all()
    return count, [_row_to_ref(row) for row in rows]


def _trace_refs_by_id(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    trace_ids: Sequence[str],
) -> dict[str, SupportingTraceRef]:
    if not trace_ids:
        return {}
    duration_ms = _trace_duration_ms()
    rows = db.execute(
        select(*_trace_ref_columns(duration_ms)).where(
            and_(
                _trace_window_filter(project_id, window),
                OtelTrace.trace_id.in_(list(trace_ids)),
            )
        )
    ).all()
    return {row.trace_id: _row_to_ref(row) for row in rows}


def _error_clusters(
    db: Session, *, project_id: uuid.UUID, window: ProjectWindow
) -> tuple[list[ErrorClusterStats], bool, bool]:
    """Deterministic ERROR-span signature clusters (bounded candidate load).

    Returns (clusters, groups_truncated, candidates_truncated).
    """
    attrs = OtelSpan.attributes
    rows = db.execute(
        select(
            OtelSpan.trace_id,
            OtelSpan.span_id,
            OtelSpan.name,
            func.left(OtelSpan.status_message, _SQL_STATUS_MESSAGE_BOUND).label(
                "status_message"
            ),
            _jsonb_string(attrs, _EXCEPTION_TYPE).label("exception_type"),
            OtelSpan.start_time,
        )
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(
            and_(
                _span_window_filter(project_id, window),
                OtelSpan.status_code == STATUS_CODE_ERROR,
            )
        )
        .order_by(OtelSpan.start_time.desc(), OtelSpan.span_id.asc())
        .limit(MAX_ERROR_SPAN_CANDIDATES + 1)
    ).all()
    candidates_truncated = len(rows) > MAX_ERROR_SPAN_CANDIDATES
    rows = rows[:MAX_ERROR_SPAN_CANDIDATES]

    grouped: OrderedDict[tuple[str, str | None, str | None], dict] = OrderedDict()
    for row in rows:
        exception_type = normalize_exception_type(row.exception_type)
        message = normalize_status_message(row.status_message)
        key = (row.name, exception_type, message)
        entry = grouped.setdefault(
            key,
            {
                "count": 0,
                "trace_ids": OrderedDict(),  # newest-first insertion order
                "span_ids": [],
            },
        )
        entry["count"] += 1
        entry["trace_ids"].setdefault(row.trace_id, None)
        if len(entry["span_ids"]) < MAX_SUPPORTING_SPAN_IDS:
            entry["span_ids"].append(row.span_id)

    ordered = sorted(
        grouped.items(),
        key=lambda item: (-item[1]["count"], item[0][0], item[0][1] or "", item[0][2] or ""),
    )
    groups_truncated = len(ordered) > MAX_ERROR_GROUPS
    ordered = ordered[:MAX_ERROR_GROUPS]

    needed_trace_ids: list[str] = []
    for _key, entry in ordered:
        needed_trace_ids.extend(
            list(entry["trace_ids"].keys())[:MAX_EXAMPLE_TRACES_PER_FINDING]
        )
    refs = _trace_refs_by_id(
        db, project_id=project_id, window=window, trace_ids=needed_trace_ids
    )

    clusters: list[ErrorClusterStats] = []
    for (span_name, exception_type, message), entry in ordered:
        example_ids = list(entry["trace_ids"].keys())[:MAX_EXAMPLE_TRACES_PER_FINDING]
        clusters.append(
            ErrorClusterStats(
                signature_label=signature_label(
                    span_name=span_name,
                    exception_type=exception_type,
                    normalized_message=message,
                ),
                span_name=span_name,
                exception_type=exception_type,
                normalized_message=message,
                occurrence_count=entry["count"],
                distinct_trace_count=len(entry["trace_ids"]),
                supporting_traces=[refs[tid] for tid in example_ids if tid in refs],
                supporting_span_ids=entry["span_ids"],
            )
        )
    return clusters, groups_truncated, candidates_truncated


def _genai_gap(
    db: Session,
    *,
    project_id: uuid.UUID,
    window: ProjectWindow,
    model_like_count: int,
    missing_model_count: int,
    missing_token_count: int,
    explicitly_classified_count: int,
) -> GenAiGapStats:
    """Attach bounded examples of model-like spans missing GenAI telemetry."""
    stats = GenAiGapStats(
        model_like_span_count=model_like_count,
        missing_model_count=missing_model_count,
        missing_token_count=missing_token_count,
        explicitly_classified_count=explicitly_classified_count,
    )
    if missing_model_count == 0 and missing_token_count == 0:
        return stats
    attrs = OtelSpan.attributes
    model = _model_expr(attrs)
    input_expr = _coalesce_numbers(attrs, INPUT_TOKEN_KEYS)
    output_expr = _coalesce_numbers(attrs, OUTPUT_TOKEN_KEYS)
    missing = or_(
        model.is_(None),
        and_(input_expr.is_(None), output_expr.is_(None)),
    )
    rows = db.execute(
        select(OtelSpan.trace_id, OtelSpan.span_id)
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(
            and_(
                _span_window_filter(project_id, window),
                _model_like_expr(attrs),
                missing,
            )
        )
        .order_by(OtelSpan.start_time.desc(), OtelSpan.span_id.asc())
        .limit(MAX_SUPPORTING_SPAN_IDS)
    ).all()
    stats.supporting_span_ids = [row.span_id for row in rows]
    example_trace_ids: list[str] = []
    for row in rows:
        if row.trace_id not in example_trace_ids:
            example_trace_ids.append(row.trace_id)
        if len(example_trace_ids) >= MAX_EXAMPLE_TRACES_PER_FINDING:
            break
    refs = _trace_refs_by_id(
        db, project_id=project_id, window=window, trace_ids=example_trace_ids
    )
    stats.supporting_traces = [
        refs[tid] for tid in example_trace_ids if tid in refs
    ]
    return stats


def collect_project_evidence(
    db: Session,
    *,
    project_id: uuid.UUID,
    current_window: ProjectWindow,
    baseline_window: ProjectWindow,
) -> ProjectWindowEvidence:
    """Run every bounded evidence query for one analysis request."""
    current = _window_aggregate(db, project_id=project_id, window=current_window)
    baseline = _window_aggregate(db, project_id=project_id, window=baseline_window)

    # Current-window span-level coverage in one aggregate pass.
    attrs = OtelSpan.attributes
    model = _model_expr(attrs)
    input_expr = _coalesce_numbers(attrs, INPUT_TOKEN_KEYS)
    output_expr = _coalesce_numbers(attrs, OUTPUT_TOKEN_KEYS)
    model_like = _model_like_expr(attrs)
    span_row = db.execute(
        select(
            _count_if(model_like).label("model_like"),
            _count_if(model.is_not(None)).label("with_model"),
            _count_if(
                or_(input_expr.is_not(None), output_expr.is_not(None))
            ).label("with_tokens"),
            _count_if(_tool_like_expr(attrs)).label("tool_like"),
            _count_if(
                and_(model_like, _explicitly_classified_expr(attrs))
            ).label("explicit"),
            _count_if(and_(model_like, model.is_(None))).label("missing_model"),
            _count_if(
                and_(
                    model_like,
                    input_expr.is_(None),
                    output_expr.is_(None),
                )
            ).label("missing_tokens"),
            func.count(func.distinct(model)).label("distinct_models"),
        )
        .select_from(OtelSpan)
        .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
        .where(_span_window_filter(project_id, current_window))
    ).one()

    distinct_services = int(
        db.scalar(
            select(func.count(func.distinct(OtelTrace.service_name))).where(
                _trace_window_filter(project_id, current_window)
            )
        )
        or 0
    )
    traces_without_root = int(
        db.scalar(
            select(func.count()).where(
                and_(
                    _trace_window_filter(project_id, current_window),
                    OtelTrace.root_span_id.is_(None),
                )
            )
        )
        or 0
    )
    parent = OtelSpan.__table__.alias("parent_span")
    orphan_count = int(
        db.scalar(
            select(func.count())
            .select_from(OtelSpan)
            .join(OtelTrace, OtelSpan.otel_trace_id == OtelTrace.id)
            .join(
                parent,
                and_(
                    parent.c.otel_trace_id == OtelSpan.otel_trace_id,
                    parent.c.span_id == OtelSpan.parent_span_id,
                ),
                isouter=True,
            )
            .where(
                and_(
                    _span_window_filter(project_id, current_window),
                    OtelSpan.parent_span_id.is_not(None),
                    parent.c.id.is_(None),
                )
            )
        )
        or 0
    )

    current_services = _service_stats(
        db,
        project_id=project_id,
        window=current_window,
        limit=MAX_SERVICES_ANALYZED,
    )
    services_truncated = distinct_services > len(current_services)
    service_names = [s.service_name for s in current_services]
    baseline_services = {
        s.service_name: s
        for s in _service_stats(
            db,
            project_id=project_id,
            window=baseline_window,
            limit=None,
            only_services=service_names,
        )
    }

    current_models = _model_stats(
        db, project_id=project_id, window=current_window, limit=MAX_MODELS_ANALYZED
    )
    distinct_models = int(span_row.distinct_models or 0)
    models_truncated = distinct_models > len(current_models)
    model_names = [m.model for m in current_models]
    baseline_models = {
        m.model: m
        for m in _model_stats(
            db,
            project_id=project_id,
            window=baseline_window,
            limit=None,
            only_models=model_names,
        )
    }

    error_examples = _trace_examples_by_service(
        db,
        project_id=project_id,
        window=current_window,
        services=service_names,
        errors_only=True,
        order_by_duration=False,
    )
    slow_examples = _trace_examples_by_service(
        db,
        project_id=project_id,
        window=current_window,
        services=service_names,
        errors_only=False,
        order_by_duration=True,
    )
    model_slow_examples = _trace_examples_by_model(
        db,
        project_id=project_id,
        window=current_window,
        models=model_names,
        by_tokens=False,
    )
    model_token_examples = _trace_examples_by_model(
        db,
        project_id=project_id,
        window=current_window,
        models=model_names,
        by_tokens=True,
    )

    outlier_count, outlier_examples = _outliers(
        db,
        project_id=project_id,
        window=current_window,
        current_p95_ms=current.p95_duration_ms,
    )

    clusters, groups_truncated, candidates_truncated = _error_clusters(
        db, project_id=project_id, window=current_window
    )

    genai = _genai_gap(
        db,
        project_id=project_id,
        window=current_window,
        model_like_count=int(span_row.model_like or 0),
        missing_model_count=int(span_row.missing_model or 0),
        missing_token_count=int(span_row.missing_tokens or 0),
        explicitly_classified_count=int(span_row.explicit or 0),
    )

    coverage = ProjectCoverage(
        current_trace_count=current.trace_count,
        baseline_trace_count=baseline.trace_count,
        current_span_count=current.span_count,
        baseline_span_count=baseline.span_count,
        current_error_trace_count=current.error_trace_count,
        baseline_error_trace_count=baseline.error_trace_count,
        services_observed=distinct_services,
        models_observed=distinct_models,
        model_like_span_count=int(span_row.model_like or 0),
        spans_with_model_data=int(span_row.with_model or 0),
        spans_with_token_data=int(span_row.with_tokens or 0),
        tool_like_span_count=int(span_row.tool_like or 0),
        traces_without_root_span=traces_without_root,
        orphan_span_count=orphan_count,
        current_sample_sparse=current.trace_count < ERROR_RATE_MIN_TRACES_PER_WINDOW,
        baseline_sample_sparse=baseline.trace_count < ERROR_RATE_MIN_TRACES_PER_WINDOW,
    )

    return ProjectWindowEvidence(
        current=current,
        baseline=baseline,
        current_services=current_services,
        baseline_services=baseline_services,
        services_truncated=services_truncated,
        current_models=current_models,
        baseline_models=baseline_models,
        models_truncated=models_truncated,
        error_examples_by_service=error_examples,
        slow_examples_by_service=slow_examples,
        slow_examples_by_model=model_slow_examples,
        token_examples_by_model=model_token_examples,
        outlier_count=outlier_count,
        outlier_examples=outlier_examples,
        error_clusters=clusters,
        error_groups_truncated=groups_truncated,
        error_span_candidates_truncated=candidates_truncated,
        genai=genai,
        coverage=coverage,
    )
