# Helios Python SDK

Lightweight client for submitting observability traces to a Helios backend via `POST /v1/traces`.

This is a **demo/portfolio SDK** — not a full OpenTelemetry integration and not production-hardened (no auth yet).

## Install (local editable)

```bash
cd sdk/python
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick start

```python
from helios_sdk import HeliosClient

client = HeliosClient(
    base_url="http://localhost:8000",
    project_slug="rag-support-bot",
    project_name="RAG Support Bot",
    environment="development",
)

trace = client.create_trace(
    user_query="How do I rotate API keys without downtime?",
    app_name="rag-support-bot",
    model="gpt-4o-mini",
)

with trace.span("retriever.search", span_type="rag") as span:
    span.set_input("api key rotation policy")
    span.set_output("Retrieved 3 policy chunks")
    span.set_metadata({"top_k": 3, "source": "docs/security.md"})

with trace.span("llm.generate", span_type="llm", provider="openai", model="gpt-4o-mini") as span:
    span.set_input("Question + retrieved context")
    span.set_output("Step-by-step rotation plan")
    span.set_tokens(1240)
    span.set_cost(0.0042)

result = client.submit_trace(trace)
print(result["trace_id"])
```

## API

| Class / method                                              | Description                       |
| ----------------------------------------------------------- | --------------------------------- |
| `HeliosClient(base_url, project_slug, ...)`                 | Configure backend URL and project |
| `create_trace(user_query, app_name, model)`                 | Start a trace builder             |
| `TraceBuilder.span(name, span_type)`                        | Context manager for a span        |
| `SpanRecorder.set_input/output/metadata/tokens/cost/status` | Attach span details               |
| `submit_trace(trace)`                                       | POST trace + spans to Helios      |

## Errors

- `HeliosConnectionError` — backend unreachable
- `HeliosAPIError` — non-2xx API response

## See also

- [examples/rag_support_bot](../../examples/rag_support_bot/) — deterministic RAG demo app
- [docs/SDK_INGESTION.md](../../docs/SDK_INGESTION.md) — end-to-end ingestion walkthrough
