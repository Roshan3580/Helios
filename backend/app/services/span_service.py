from sqlalchemy.orm import Session

from app.models import Span, Trace
from app.schemas import SpanCreate
from app.utils.ids import generate_id


def add_spans_to_trace(db: Session, trace: Trace, spans: list[SpanCreate]) -> list[Span]:
    created: list[Span] = []
    for payload in spans:
        span = Span(
            trace_id=trace.id,
            span_id=payload.span_id or generate_id("spn"),
            parent_span_id=payload.parent_span_id,
            name=payload.name,
            span_type=payload.span_type,
            provider=payload.provider,
            model=payload.model,
            latency_ms=payload.latency_ms,
            token_count=payload.token_count,
            cost_usd=payload.cost_usd,
            status=payload.status,
            input_preview=payload.input_preview,
            output_preview=payload.output_preview,
            metadata_json=payload.metadata_json,
            started_at=payload.started_at,
            ended_at=payload.ended_at,
        )
        db.add(span)
        created.append(span)
    db.flush()
    return created
