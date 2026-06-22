from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import EvaluationRun, RagChunkMetric, RagChunkStatus, Trace, TraceStatus


def _chunk_to_read(chunk: RagChunkMetric) -> dict:
    return {
        "id": chunk.id,
        "chunk_ref": chunk.chunk_ref,
        "retrieval_hits": chunk.retrieval_hits,
        "quality_score": chunk.quality_score,
        "status": chunk.status,
        "created_at": chunk.created_at,
    }


def get_rag_metrics(db: Session, *, project_slug: str | None = None) -> dict:
    chunk_stmt = select(RagChunkMetric)
    if project_slug:
        chunk_stmt = chunk_stmt.join(RagChunkMetric.project).where(
            RagChunkMetric.project.has(slug=project_slug)
        )
    chunks = db.scalars(chunk_stmt.order_by(RagChunkMetric.retrieval_hits.desc())).all()

    trace_stmt = select(Trace)
    if project_slug:
        trace_stmt = trace_stmt.join(Trace.project).where(Trace.project.has(slug=project_slug))
    traces = db.scalars(trace_stmt).all()

    eval_stmt = select(EvaluationRun)
    if project_slug:
        eval_stmt = eval_stmt.join(EvaluationRun.project).where(
            EvaluationRun.project.has(slug=project_slug)
        )
    eval_runs = db.scalars(eval_stmt).all()

    chunk_metrics = [_chunk_to_read(chunk) for chunk in chunks]

    if chunks:
        ok_hits = sum(
            chunk.retrieval_hits for chunk in chunks if chunk.status == RagChunkStatus.ok
        )
        total_hits = sum(chunk.retrieval_hits for chunk in chunks)
        retrieval_hit_rate = ok_hits / total_hits if total_hits else 0.0
        avg_chunk_quality = sum(chunk.quality_score for chunk in chunks) / len(chunks)
    else:
        retrieval_hit_rate = 0.0
        avg_chunk_quality = 0.0

    citation_coverage = (
        sum(run.citation_coverage for run in eval_runs) / len(eval_runs) if eval_runs else 0.0
    )

    rag_traces = [trace for trace in traces if "rag" in trace.app_name]
    missing_source_rate = (
        sum(1 for trace in rag_traces if trace.status != TraceStatus.success) / len(rag_traces)
        if rag_traces
        else 0.0
    )

    low_confidence_queries = [
        trace.user_query
        for trace in traces
        if trace.status == TraceStatus.warning
    ]
    top_failing_queries = [
        trace.user_query
        for trace in traces
        if trace.status in (TraceStatus.error, TraceStatus.warning)
    ][:5]

    return {
        "retrieval_hit_rate": round(retrieval_hit_rate, 4),
        "citation_coverage": round(citation_coverage, 4),
        "missing_source_rate": round(missing_source_rate, 4),
        "avg_chunk_quality": round(avg_chunk_quality, 4),
        "low_confidence_queries": low_confidence_queries,
        "top_failing_queries": top_failing_queries,
        "chunk_metrics": chunk_metrics,
        "demo": True,
    }
