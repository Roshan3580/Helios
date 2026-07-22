"""Shared payload builders for backend tests."""

from datetime import datetime, timedelta, timezone

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_span(
    span_id: str,
    parent_span_id: str | None,
    name: str,
    span_type: str,
    offset_ms: int,
    duration_ms: int,
    **extra,
) -> dict:
    started = BASE_TIME + timedelta(milliseconds=offset_ms)
    ended = started + timedelta(milliseconds=duration_ms)
    span = {
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "span_type": span_type,
        "latency_ms": duration_ms,
        "status": "success",
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
    }
    span.update(extra)
    return span


def make_trace_payload(
    trace_id: str = "trc_test0001",
    project_slug: str = "test-project",
    **overrides,
) -> dict:
    """A representative nested trace: input -> (rag, llm -> tool)."""
    payload = {
        "trace_id": trace_id,
        "project_slug": project_slug,
        "project_name": "Test Project",
        "environment": "test",
        "user_query": "How do I rotate API keys without downtime?",
        "app_name": "rag.test_app",
        "model": "gpt-4o-mini",
        "status": "success",
        "latency_ms": 1160,
        "total_tokens": 1500,
        "prompt_tokens": 1100,
        "completion_tokens": 400,
        "estimated_cost_usd": 0.0042,
        "spans": [
            make_span(f"{trace_id}_input", None, "user.query", "input", 0, 5,
                      input_preview="How do I rotate API keys without downtime?"),
            make_span(f"{trace_id}_rag", f"{trace_id}_input",
                      "retriever.search", "rag", 10, 180,
                      provider="local-index",
                      metadata_json={"top_k": 3}),
            make_span(f"{trace_id}_llm", f"{trace_id}_input",
                      "llm.generate", "llm", 200, 800,
                      provider="openai", model="gpt-4o-mini",
                      token_count=1500, cost_usd=0.0042,
                      output_preview="Create a new key, migrate, revoke."),
            make_span(f"{trace_id}_tool", f"{trace_id}_llm",
                      "tool.lookup_policy", "tool", 1010, 150),
        ],
    }
    payload.update(overrides)
    return payload
