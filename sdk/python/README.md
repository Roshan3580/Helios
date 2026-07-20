# Helios Python SDK

One distribution, two APIs:

- **v2 `Helios` runtime (recommended)** — exports standard OpenTelemetry spans
  through authenticated OTLP/HTTP protobuf to `/v1/otlp/traces`, with automatic
  OpenAI instrumentation. Requires the `[otel]` extra (`[openai]` for OpenAI).
- **Legacy `HeliosClient`** — submits a custom JSON trace to `/v1/traces`.
  Dependency-light; kept for backward compatibility.

## Install

```bash
# v2 runtime + OpenAI auto-instrumentation
pip install -e "sdk/python[otel,openai]"

# legacy client only (no OpenTelemetry)
pip install -e "sdk/python"
```

## v2 quick start

```python
import os
from helios_sdk import Helios

helios = Helios.configure(
    api_key=os.environ["HELIOS_API_KEY"],   # project API key (a secret)
    service_name="my-agent",
    # endpoint defaults to http://localhost:8000
)

helios.instrument_openai()  # prompt/response content is NOT captured by default

# Manual spans for custom workflow boundaries:
with helios.agent("my-agent"):
    with helios.retrieval("kb.search") as span:
        span.set_attribute("retrieval.top_k", 5)
    with helios.tool("lookup_policy") as span:
        span.set_attribute("tool.name", "policy-engine")

@helios.trace("answer-question")           # sync or async functions
def answer_question(q): ...

helios.force_flush()   # before a short-lived process exits
helios.shutdown()      # idempotent; also runs at process exit
```

### Environment variables (precedence: explicit arg > Helios env > OTel env > default)

| Variable | Purpose | Default |
| --- | --- | --- |
| `HELIOS_API_KEY` | project API key (bearer) | required |
| `HELIOS_ENDPOINT` | backend base URL | `http://localhost:8000` |
| `HELIOS_SERVICE_NAME` | `service.name` | required unless `OTEL_SERVICE_NAME` set |
| `HELIOS_ENVIRONMENT` | deployment environment | unset |
| `HELIOS_CAPTURE_CONTENT` | capture prompt/response content | `false` |

### Privacy

Prompt and completion content are **disabled by default**. Enabling capture
(`HELIOS_CAPTURE_CONTENT=true` or `instrument_openai(capture_content=True)`) may
send sensitive data to Helios; you are responsible for consent, redaction, and
data-handling. Helios never logs prompts/responses. **API keys are secrets** —
never commit them or ship them to browser code.

### Lifecycle

- `force_flush()` — force-export buffered spans (call before a short-lived or
  serverless process returns).
- `shutdown()` — flush and stop telemetry; idempotent; also registered at exit.

### Compatibility

- Auto-instrumentation this release: **OpenAI** only, via the official
  `opentelemetry-instrumentation-openai-v2` (beta). Verified with `openai`
  2.46.0 on Python ≥3.10. Other providers/frameworks are future work.
- A Node.js/TypeScript SDK also ships in this repository
  (`sdk/typescript`, `@helios-ai/sdk` — repository artifact, not yet published
  to npm); see [docs/TYPESCRIPT_SDK.md](../../docs/TYPESCRIPT_SDK.md).
- The legacy `HeliosClient` (below) continues to target `/v1/traces`.

---

## Legacy client (`HeliosClient` → `/v1/traces`)

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

- `HeliosConnectionError`: backend unreachable
- `HeliosAPIError`: non-2xx API response

## See also

- [examples/python_sdk_quickstart](../../examples/python_sdk_quickstart/): v2 `Helios` runtime + OpenAI auto-instrumentation demo
- [docs/ADR_003_PYTHON_OTEL_SDK.md](../../docs/ADR_003_PYTHON_OTEL_SDK.md): v2 SDK decision record
- [examples/rag_support_bot](../../examples/rag_support_bot/): deterministic legacy RAG demo app
- [docs/SDK_INGESTION.md](../../docs/SDK_INGESTION.md): legacy end-to-end ingestion walkthrough
