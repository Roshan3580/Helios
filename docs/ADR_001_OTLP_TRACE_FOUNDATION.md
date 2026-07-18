# ADR 001: OTLP/HTTP Protobuf Trace Foundation (Helios v2)

Status: Accepted · Branch: `helios-v2-otel-foundation`

## Context

Helios v1 ingests traces through a custom JSON contract (`POST /v1/traces`)
into denormalized `traces`/`spans` tables that require GenAI-specific fields
(user query, model, token counts, cost) at the trace level and trust
client-supplied aggregates. That model cannot represent standard
OpenTelemetry data and blocks interoperability with existing OTel
instrumentation.

## Decision

### Adopt OTLP/HTTP protobuf as the canonical ingestion protocol

- OTLP is the industry-standard telemetry wire format; every OTel SDK ships
  an OTLP/HTTP protobuf exporter, so any instrumented app can send to Helios
  with zero custom client code.
- Protobuf is the mandatory OTLP encoding; parsing uses the official
  generated classes from `opentelemetry-proto` (the only new production
  backend dependency — the full OTel SDK/exporter is dev/example-only,
  since the backend receives telemetry rather than emitting it).
- The legacy JSON and OTLP protobuf contracts are **not multiplexed on one
  route**: `POST /v1/otlp/traces` accepts only `application/x-protobuf`.

### Keep legacy `/v1/traces` temporarily

The v1 endpoint, tables, Python SDK, frontend, and tests stay untouched so
the deployed demo keeps working while v2 is built alongside. Removal happens
only after the frontend and SDK migrate to the v2 path in later batches; no
removal date is set here — the boundary is "when no consumer reads or writes
the legacy path anymore."

### Separate v2 telemetry store

New tables `otel_traces` and `otel_spans` (migration `002_otel_foundation`)
are independent of the seeded v1 analytics schema because:

- v1 rows mix genuinely ingested data with demo-seeded analytics; the v2
  store must contain only real telemetry an analyst can trust.
- OTel identity rules conflict with v1 constraints (v1 `spans.span_id` is
  globally unique; OTel span IDs are unique only within a trace — v2 scopes
  uniqueness to `(project_id, trace_id, span_id)`).
- Trace-level GenAI fields are deliberately absent in v2; model/token/cost
  signals live in span attributes exactly as sent and will be derived, never
  fabricated.

Trace summaries (`start/end`, span/error counts, root span) are always
recomputed from stored spans; client-side trace aggregates are never trusted.

**Span re-send policy:** span identity is `(project_id, trace_id, span_id)`;
re-sending an identical batch is a no-op (idempotent upsert), and re-sending
a span ID with changed content deterministically overwrites the stored span
(last write wins). `created_at`/`first_seen_at` are preserved;
`updated_at`/`last_seen_at` advance.

**Batch semantics:** an export succeeds or fails as a whole. Any invalid
span (wrong-length or all-zero IDs, undecodable protobuf) rejects the entire
request with 4xx and nothing is persisted. Partial success is not claimed
(`ExportTraceServiceResponse.partial_success` is never set).

### Defer OTLP/gRPC

OTLP/HTTP covers every OTel SDK (gRPC exporters can also fall back to HTTP).
gRPC requires a second server runtime alongside FastAPI/uvicorn for little
demo-phase benefit. Revisit when a collector or high-volume ingestion is on
the roadmap.

### Defer authentication; require explicit project identification now

Auth (project-scoped API keys) is the next security batch. Until then the v2
path enforces scoping discipline without credentials:

- **Ingestion** requires a non-empty `X-Helios-Project-Slug` header
  (optional `X-Helios-Environment` as an environment fallback when the
  resource lacks `deployment.environment(.name)`).
- **Reads** (`/v2/traces*`) require an explicit `project_slug` query
  parameter; unscoped queries are impossible, and the same `trace_id` in
  another project is invisible (404).

These headers/params are a **temporary compatibility mechanism**: API keys
will replace or resolve them, and header-based project selection must not be
treated as a security control (nor is CORS).

## Component classification

| Component | Status |
| --- | --- |
| `POST /v1/otlp/traces` | Canonical v2 ingestion |
| `otel_traces`, `otel_spans` tables | Canonical v2 store |
| `GET /v2/traces`, `GET /v2/traces/{trace_id}` | Canonical v2 reads |
| `examples/otel_quickstart` | Canonical v2 reference client |
| `POST /v1/traces`, `traces`/`spans` tables | Legacy compatibility |
| `sdk/python/helios_sdk`, `examples/rag_support_bot` | Legacy compatibility |
| Frontend `/app/*` pages, seeded analytics tables | Legacy compatibility (migrate in later batches) |

## Consequences

- Two parallel trace stores exist until the frontend/SDK migration; the
  dashboard does not yet read v2 data.
- Request-size limit (4 MiB) and slug validation are application-level;
  rate limiting and auth remain open security items for the next batch.
- Nanosecond timestamps are truncated to microseconds in `TIMESTAMPTZ`
  columns; exact durations are preserved in `duration_ns`.
