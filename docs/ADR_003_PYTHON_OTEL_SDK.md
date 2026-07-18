# ADR 003: Python OpenTelemetry SDK and OpenAI Auto-Instrumentation

Status: Accepted · Branch: `helios-v2-otel-foundation` · Builds on
[ADR 001](ADR_001_OTLP_TRACE_FOUNDATION.md) (OTLP store) and
[ADR 002](ADR_002_PROJECT_API_KEYS.md) (project keys).

## Context

The canonical v2 path ingests OTLP/HTTP protobuf authenticated by project API
keys. Until now the only client was the legacy builder SDK (`HeliosClient` →
`/v1/traces`, a custom JSON contract). Developers need a low-friction way to send
standard OpenTelemetry spans — including automatic OpenAI tracing — to Helios.

## Decision

### The v2 SDK exports standard OpenTelemetry spans

`Helios.configure(...)` builds a standard OTel `TracerProvider` + `BatchSpanProcessor`
+ OTLP/HTTP protobuf exporter targeting `/v1/otlp/traces`. Spans are ordinary
OTel spans, so any OTel instrumentation composes with Helios and no custom trace
model is introduced on the client. Authentication is `Authorization: Bearer
<project key>`; the project is derived server-side from the key (no slug header).

### The legacy builder SDK remains, temporarily

`HeliosClient` / `TraceBuilder` / `SpanRecorder` and `/v1/traces` are unchanged
and dependency-light (no OpenTelemetry required). They stay for backward
compatibility until callers migrate to the v2 runtime; no removal date is set.

### One distribution, additive API, optional extras

A single `helios-sdk` distribution keeps both APIs. `import helios_sdk` never
imports OpenTelemetry — `Helios` is exposed via a lazy module `__getattr__`, so
legacy users are not forced to install OTel or OpenAI. Dependency groups:

- `[otel]` — `opentelemetry-api/sdk`, `opentelemetry-exporter-otlp-proto-http`
  (`>=1.30,<2`). Required by the v2 runtime.
- `[openai]` — `opentelemetry-instrumentation-openai-v2` (`>=2.0b0,<3`) and
  `openai` (`>=1.26,<3`). Required only for OpenAI auto-instrumentation.
- `[dev]` — the above plus `pytest`.

### Public initialization API

`Helios.configure(api_key=, service_name=, endpoint=, environment=,
capture_content=, timeout=)`. Configuration precedence: explicit argument >
Helios env var (`HELIOS_API_KEY`, `HELIOS_ENDPOINT`, `HELIOS_SERVICE_NAME`,
`HELIOS_ENVIRONMENT`, `HELIOS_CAPTURE_CONTENT`) > recognized OTel env var
(`OTEL_SERVICE_NAME`) > default. Endpoint defaults to `http://localhost:8000`
and the canonical traces URL is derived as `<endpoint>/v1/otlp/traces`.
`configure()` performs no network I/O; imports never touch the global provider.
The API key is never logged and never appears in `repr`/`str`/exceptions.

### Existing tracer-provider handling

- No real SDK provider installed → Helios creates one and sets it globally
  (owns it).
- A compatible SDK `TracerProvider` already installed → Helios attaches only its
  `BatchSpanProcessor` and does not replace the provider (does not call
  `set_tracer_provider`). Note: resource attributes such as `service.name` then
  come from the host provider.
- A foreign/non-SDK provider → Helios raises rather than replacing another
  vendor's provider.

Repeated identical `configure()` is idempotent (returns the same instance, no
duplicate processor). Conflicting `configure()` raises and requires `shutdown()`
first. `configure()` after `shutdown()` re-initializes cleanly.

### Batch export and shutdown

Normal operation uses `BatchSpanProcessor`. `force_flush()` and `shutdown()` are
public; `shutdown()` is idempotent and also registered via `atexit` (safe
because idempotent). Short-lived/serverless processes should `force_flush()`
before exit.

### Privacy / content-capture defaults

Content capture is **off by default**. The OpenAI instrumentor's content mode is
controlled in one place via `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT`
(`NO_CONTENT` by default; `SPAN_ONLY` when opted in, so content lands in span
attributes the trace exporter sends — Helios ingests traces, not logs). Opt-in
is `HELIOS_CAPTURE_CONTENT=true` or `instrument_openai(capture_content=True)`.
Helios never logs prompts or responses.

### Initial automatic integration: OpenAI

`helios.instrument_openai()` uses the maintained official
`opentelemetry-instrumentation-openai-v2` instrumentor (imported lazily; a
missing `[openai]` extra raises an actionable error). It is idempotent (guards on
`is_instrumented_by_opentelemetry`), binds to Helios's tracer provider, supports
the sync and async OpenAI clients, preserves official GenAI semantic-convention
attributes (operation, model, token usage, status/errors), and offers
`uninstrument_openai()`.

Selected package: **`opentelemetry-instrumentation-openai-v2` 2.4b0** (beta),
requires Python ≥3.10, `openai>=1.26.0`; verified against `openai` 2.46.0 and
OpenTelemetry 1.44.0 / semconv 0.65b0.

### Manual semantic helpers

`helios.agent/retrieval/tool/llm/span(...)` context managers and a
`@helios.trace(...)` decorator (sync + async, `functools.wraps`-preserving) use
standard OTel context propagation and span kinds. They record unhandled
exceptions, set OTel `ERROR` status, and re-raise unchanged. Attribute values are
normalized to OTel-safe types. Semantic attribute names are centralized in
`helios_sdk/semconv.py`; GenAI attributes are set only from explicit caller
input — no token/cost/model/prompt/response/retrieval/eval values are fabricated.
`helios.tracer` exposes the raw tracer for advanced use.

### Why other frameworks and TypeScript are deferred

This checkpoint ships one integration (OpenAI) to keep scope bounded and the
instrumentor's beta surface contained. Additional providers/frameworks
(Anthropic, LangChain, LlamaIndex, …) and a TypeScript SDK are future work and
are deliberately not claimed as supported.

## Consequences

- Two client SDKs coexist until legacy callers migrate.
- The OpenAI instrumentor is **beta**; its attribute set and content-mode
  controls may shift across releases (bounded `<3`, verified at 2.4b0).
- In attach-to-existing-provider mode, Helios cannot override the host provider's
  resource, so `service.name` may reflect the host configuration.
