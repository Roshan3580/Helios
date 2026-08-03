# Helios Observatory Python SDK

`helios-observatory-sdk` adds OpenTelemetry tracing to Python applications and
exports authenticated OTLP/HTTP protobuf spans to Helios. It supports manual
agent, retrieval, tool, LLM, and workflow spans plus optional OpenAI
auto-instrumentation.

The distribution name is `helios-observatory-sdk`. The Python import remains
`helios_sdk`.

Helios is currently a production-capable hosted beta. It is not a generally
available or SLA-backed service.

## Installation

Install only the dependency-light legacy client:

```bash
pip install helios-observatory-sdk
```

Install the recommended OpenTelemetry runtime:

```bash
pip install "helios-observatory-sdk[otel]"
```

Install the runtime with OpenAI auto-instrumentation:

```bash
pip install "helios-observatory-sdk[openai]"
```

The combined and all-inclusive forms are also supported:

```bash
pip install "helios-observatory-sdk[otel,openai]"
pip install "helios-observatory-sdk[all]"
```

The `openai` extra includes the OpenTelemetry runtime it needs. Development and
test dependencies are not installed by any runtime extra.

## OpenTelemetry quick start

Create a project API key in Helios with `traces:ingest` access, then inject it
through your local secret-management mechanism. Never commit a `hel_proj_*`
key, print it, or place it in browser code.

```python
import os

from helios_sdk import Helios

helios = Helios.configure(
    api_key=os.environ["HELIOS_API_KEY"],
    service_name="my-agent",
    endpoint=os.environ.get("HELIOS_ENDPOINT", "http://localhost:8000"),
    environment="development",
)

with helios.agent("answer-question"):
    with helios.retrieval("knowledge.search") as span:
        span.set_attribute("retrieval.top_k", 5)
    with helios.tool("policy.lookup") as span:
        span.set_attribute("tool.name", "policy-engine")

flush_completed = helios.force_flush()
helios.shutdown()
if not flush_completed:
    raise SystemExit(
        "Export did not complete locally. Review exporter errors before retrying."
    )

print(
    "Export completed locally. Check Helios to confirm trace arrival. "
    "Exporter errors are authoritative."
)
```

`force_flush()` confirms that the local OpenTelemetry processor completed its
work. It does not prove that the backend accepted the trace because the
OpenTelemetry batch processor does not propagate the exporter result. Verify
trace arrival in Helios before claiming successful delivery.

An invalid or revoked project key remains rejected by Helios with HTTP 401.
The SDK does not retry with another credential or convert that rejection into
success. OpenTelemetry exporter errors are authoritative.

## Endpoint and environment configuration

Explicit arguments take precedence over Helios environment variables, which
take precedence over recognized OpenTelemetry variables and defaults.

| Variable | Purpose | Default |
| --- | --- | --- |
| `HELIOS_API_KEY` | Project API key used as the bearer credential | Required |
| `HELIOS_ENDPOINT` | Helios backend base URL | `http://localhost:8000` |
| `HELIOS_SERVICE_NAME` | OpenTelemetry `service.name` | `OTEL_SERVICE_NAME`, then required |
| `HELIOS_ENVIRONMENT` | Deployment environment resource attribute | Unset |
| `HELIOS_CAPTURE_CONTENT` | Opt in to prompt and response capture | `false` |

The SDK appends `/v1/otlp/traces` to a base endpoint. A full endpoint already
ending in that canonical path is accepted without duplicating it.

## OpenAI instrumentation

Install the `openai` extra before enabling instrumentation:

```python
import os

from helios_sdk import Helios
from openai import OpenAI

helios = Helios.configure(
    api_key=os.environ["HELIOS_API_KEY"],
    service_name="openai-agent",
    endpoint=os.environ.get("HELIOS_ENDPOINT", "http://localhost:8000"),
)
helios.instrument_openai()

client = OpenAI()

with helios.agent("openai-agent"):
    client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Hello"}],
    )

helios.force_flush()
helios.shutdown()
```

Prompt and completion content capture is disabled by default. Enabling
`HELIOS_CAPTURE_CONTENT=true` or passing `capture_content=True` may transmit
sensitive content. You are responsible for consent, redaction, and applicable
data-handling requirements.

## Decorators and manual spans

`Helios.trace()` decorates synchronous or asynchronous workflow functions:

```python
@helios.trace("answer-question")
def answer_question(question: str) -> str:
    with helios.tool("policy.lookup"):
        return "answer"
```

The runtime also exposes `agent`, `retrieval`, `tool`, `llm`, and general
`span` context managers. Raw OpenTelemetry access remains available through
`helios.tracer`.

## Legacy client

The base installation retains the dependency-light `HeliosClient` API for the
legacy `/v1/traces` JSON endpoint:

```python
from helios_sdk import HeliosClient

client = HeliosClient(
    base_url="http://localhost:8000",
    project_slug="example",
    project_name="Example",
    environment="development",
)

trace = client.create_trace(
    user_query="How do I rotate a key?",
    app_name="support-agent",
    model="example-model",
)

with trace.span("policy.lookup", span_type="tool") as span:
    span.set_output("Rotation guidance retrieved")

result = client.submit_trace(trace)
print(result["trace_id"])
```

`HeliosConnectionError` reports an unreachable backend.
`HeliosAPIError` reports a non-success HTTP response.

## Version and compatibility

The installed distribution exposes its metadata version as
`helios_sdk.__version__`. Version `0.2.0` supports Python 3.10 through 3.13.
Artifact installation and SDK tests cover each advertised Python version in
ordinary CI.

The package is pure Python. OpenAI auto-instrumentation uses the upstream
`opentelemetry-instrumentation-openai-v2` package and does not imply affiliation
with OpenAI or OpenTelemetry.

## Project links

- Repository: https://github.com/Roshan3580/Helios
- Issues: https://github.com/Roshan3580/Helios/issues
- Documentation: https://github.com/Roshan3580/Helios/tree/main/docs
- Hosted beta: https://helios-staging-tau.vercel.app
- Python SDK example: https://github.com/Roshan3580/Helios/tree/main/examples/python_sdk_quickstart

## License

Copyright 2026 Roshan Raj.

Helios Observatory Python SDK is licensed under the Apache License, Version
2.0. See https://github.com/Roshan3580/Helios/blob/main/LICENSE.
