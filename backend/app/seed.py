from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    EvaluationRun,
    Project,
    PromptVersion,
    RagChunkMetric,
    RagChunkStatus,
    Span,
    SpanStatus,
    SpanType,
    Trace,
    TraceStatus,
)
from app.schemas import SeedResponse, SpanCreate, TraceCreate
from app.services.project_service import get_or_create_project
from app.services.trace_service import create_trace, utc_now


def _span(
    *,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    span_type: SpanType,
    offset_ms: int,
    duration_ms: int,
    model: str | None = None,
    provider: str | None = None,
    token_count: int | None = None,
    cost_usd: float | None = None,
    status: SpanStatus = SpanStatus.success,
    input_preview: str | None = None,
    output_preview: str | None = None,
    metadata: dict | None = None,
    base: datetime,
) -> SpanCreate:
    started = base + timedelta(milliseconds=offset_ms)
    ended = started + timedelta(milliseconds=duration_ms)
    return SpanCreate(
        span_id=span_id,
        parent_span_id=parent_span_id,
        name=name,
        span_type=span_type,
        provider=provider,
        model=model,
        latency_ms=duration_ms,
        token_count=token_count,
        cost_usd=cost_usd,
        status=status,
        input_preview=input_preview,
        output_preview=output_preview,
        metadata_json={**(metadata or {}), "demo": True},
        started_at=started,
        ended_at=ended,
    )


def _build_trace_spans(trace_key: str, base: datetime, *, include_rag: bool, include_tool: bool) -> list[SpanCreate]:
    input_id = f"{trace_key}_input"
    spans: list[SpanCreate] = [
        _span(
            span_id=input_id,
            parent_span_id=None,
            name="user.query",
            span_type=SpanType.input,
            offset_ms=0,
            duration_ms=6,
            input_preview="User message received",
            base=base,
        ),
    ]

    if include_rag:
        spans.extend(
            [
                _span(
                    span_id=f"{trace_key}_rag",
                    parent_span_id=input_id,
                    name="retriever.pgvector",
                    span_type=SpanType.rag,
                    offset_ms=12,
                    duration_ms=184,
                    provider="pgvector",
                    metadata={"chunks_retrieved": 5},
                    base=base,
                ),
                _span(
                    span_id=f"{trace_key}_rerank",
                    parent_span_id=input_id,
                    name="reranker.cohere",
                    span_type=SpanType.rag,
                    offset_ms=198,
                    duration_ms=142,
                    provider="cohere",
                    base=base,
                ),
            ]
        )

    llm_start = 342 if include_rag else 20
    llm_id = f"{trace_key}_llm"
    spans.append(
        _span(
            span_id=llm_id,
            parent_span_id=input_id,
            name="llm.generate",
            span_type=SpanType.llm,
            offset_ms=llm_start,
            duration_ms=812 if include_rag else 640,
            provider="openai" if include_rag else "anthropic",
            model="gpt-4o" if include_rag else "claude-3.5",
            token_count=1800,
            cost_usd=0.012,
            base=base,
        )
    )

    if include_tool:
        spans.append(
            _span(
                span_id=f"{trace_key}_tool",
                parent_span_id=llm_id,
                name="tool.lookup_policy",
                span_type=SpanType.tool,
                offset_ms=llm_start + 820,
                duration_ms=198,
                status=SpanStatus.error,
                output_preview="Tool timeout after 198ms",
                base=base,
            )
        )

    spans.append(
        _span(
            span_id=f"{trace_key}_output",
            parent_span_id=input_id,
            name="response.finalize",
            span_type=SpanType.output,
            offset_ms=llm_start + 1020,
            duration_ms=52,
            output_preview="Assistant response assembled",
            base=base,
        )
    )
    return spans


DEMO_TRACES: list[dict] = [
    {
        "trace_id": "trc_8f2a31e",
        "user_query": "What changed in the Q3 revenue policy?",
        "app_name": "agent.research_assistant",
        "model": "gpt-4o",
        "status": TraceStatus.success,
        "latency_ms": 1420,
        "total_tokens": 2341,
        "prompt_tokens": 1820,
        "completion_tokens": 521,
        "estimated_cost_usd": 0.018,
        "include_rag": True,
        "include_tool": True,
    },
    {
        "trace_id": "trc_7c1f902",
        "user_query": "How do I rotate API keys without downtime?",
        "app_name": "agent.support_router",
        "model": "gpt-4o",
        "status": TraceStatus.success,
        "latency_ms": 980,
        "total_tokens": 1842,
        "prompt_tokens": 1400,
        "completion_tokens": 442,
        "estimated_cost_usd": 0.011,
        "include_rag": False,
        "include_tool": False,
    },
    {
        "trace_id": "trc_4a90b21",
        "user_query": "Is there a SOC 2 type II report available?",
        "app_name": "rag.knowledge_base",
        "model": "claude-3.5",
        "status": TraceStatus.warning,
        "latency_ms": 1810,
        "total_tokens": 2003,
        "prompt_tokens": 1500,
        "completion_tokens": 503,
        "estimated_cost_usd": 0.014,
        "include_rag": True,
        "include_tool": False,
    },
    {
        "trace_id": "trc_91b2c77",
        "user_query": "Can I export traces to datadog?",
        "app_name": "agent.support_router",
        "model": "gemini-1.5",
        "status": TraceStatus.error,
        "latency_ms": 2410,
        "total_tokens": 1980,
        "prompt_tokens": 1200,
        "completion_tokens": 780,
        "estimated_cost_usd": 0.009,
        "include_rag": False,
        "include_tool": True,
    },
    {
        "trace_id": "trc_2c0a18e",
        "user_query": "Refund window for annual plans?",
        "app_name": "rag.knowledge_base",
        "model": "gpt-4o",
        "status": TraceStatus.success,
        "latency_ms": 1320,
        "total_tokens": 1721,
        "prompt_tokens": 1300,
        "completion_tokens": 421,
        "estimated_cost_usd": 0.012,
        "include_rag": True,
        "include_tool": False,
    },
]


def seed_demo_data(db: Session) -> SeedResponse:
    project = get_or_create_project(
        db,
        slug="acme",
        name="Acme Corp",
        environment="production",
    )

    existing_trace_ids = set(
        db.scalars(select(Trace.trace_id).where(Trace.project_id == project.id)).all()
    )

    traces_seeded = 0
    base_time = utc_now() - timedelta(hours=2)

    for index, item in enumerate(DEMO_TRACES):
        if item["trace_id"] in existing_trace_ids:
            continue

        trace_base = base_time + timedelta(minutes=index * 7)
        payload = TraceCreate(
            trace_id=item["trace_id"],
            project_slug=project.slug,
            project_name=project.name,
            environment=project.environment,
            user_query=item["user_query"],
            app_name=item["app_name"],
            model=item["model"],
            status=item["status"],
            latency_ms=item["latency_ms"],
            total_tokens=item["total_tokens"],
            prompt_tokens=item["prompt_tokens"],
            completion_tokens=item["completion_tokens"],
            estimated_cost_usd=item["estimated_cost_usd"],
            spans=_build_trace_spans(
                item["trace_id"],
                trace_base,
                include_rag=item["include_rag"],
                include_tool=item["include_tool"],
            ),
        )
        create_trace(db, payload)
        traces_seeded += 1

    db.execute(delete(PromptVersion).where(PromptVersion.project_id == project.id))
    prompt_rows = [
        PromptVersion(
            project_id=project.id,
            name="support.router.system",
            version="v6",
            model="gpt-4o",
            eval_score=88.1,
            latency_ms=1510,
            cost_usd=0.02,
        ),
        PromptVersion(
            project_id=project.id,
            name="research.summarizer",
            version="v4",
            model="claude-3.5",
            eval_score=91.4,
            latency_ms=1780,
            cost_usd=0.015,
        ),
        PromptVersion(
            project_id=project.id,
            name="rag.answer.synth",
            version="v9",
            model="gpt-4o",
            eval_score=84.7,
            latency_ms=1320,
            cost_usd=0.012,
        ),
    ]
    db.add_all(prompt_rows)

    db.execute(delete(EvaluationRun).where(EvaluationRun.project_id == project.id))
    eval_rows = [
        EvaluationRun(
            project_id=project.id,
            dataset_name="support_qa.v4",
            prompt_name="support.router.system",
            model="gpt-4o",
            accuracy=0.881,
            citation_coverage=0.76,
            latency_ms=1510,
            cost_usd=0.02,
            status="completed",
        ),
        EvaluationRun(
            project_id=project.id,
            dataset_name="policy_retrieval.v1",
            prompt_name="rag.answer.synth",
            model="gpt-4o",
            accuracy=0.847,
            citation_coverage=0.68,
            latency_ms=1320,
            cost_usd=0.012,
            status="completed",
        ),
    ]
    db.add_all(eval_rows)

    db.execute(delete(RagChunkMetric).where(RagChunkMetric.project_id == project.id))
    rag_rows = [
        RagChunkMetric(
            project_id=project.id,
            chunk_ref="policy/revenue-q3.md#refunds",
            retrieval_hits=142,
            quality_score=0.91,
            status=RagChunkStatus.ok,
        ),
        RagChunkMetric(
            project_id=project.id,
            chunk_ref="security/soc2-overview.pdf",
            retrieval_hits=88,
            quality_score=0.74,
            status=RagChunkStatus.drift,
        ),
        RagChunkMetric(
            project_id=project.id,
            chunk_ref="billing/annual-refunds.md",
            retrieval_hits=51,
            quality_score=0.62,
            status=RagChunkStatus.low,
        ),
    ]
    db.add_all(rag_rows)

    db.flush()

    return SeedResponse(
        project_slug=project.slug,
        traces_seeded=traces_seeded,
        prompt_versions_seeded=len(prompt_rows),
        evaluation_runs_seeded=len(eval_rows),
        rag_chunk_metrics_seeded=len(rag_rows),
        demo=True,
    )
