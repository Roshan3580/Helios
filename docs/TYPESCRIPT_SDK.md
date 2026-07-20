# Helios TypeScript SDK (`@helios-ai/sdk`)

Node.js server SDK exporting canonical OpenTelemetry traces to Helios over
OTLP/HTTP **protobuf** with project API-key authentication. Source lives in
[`sdk/typescript/`](../sdk/typescript/); the package README
([sdk/typescript/README.md](../sdk/typescript/README.md)) is the API-level
reference. This document covers repository integration and design decisions.

> **Publication status:** the name `@helios-ai/sdk` (version 0.1.0) is
> reserved for publication and **not yet published to npm**. The only
> supported installation path today is the repository artifact
> (`npm pack` → install the tarball, or `file:` dependency), which is what CI
> verifies. Do not document or advertise a public `npm install` until
> publication happens.

## Support matrix

| Requirement | Value |
| ----------- | ----- |
| Node.js | `^18.19.0 \|\| >=20.6.0` (OpenTelemetry JS SDK 2.x window; enforced via `engines`) |
| TypeScript (consumers) | ≥ 5.0 (developed/verified against 5.9; NodeNext + Bundler resolution both work) |
| Module systems | ESM **and** CommonJS (dual build, both consumer-tested) |
| `openai` (optional instrumentation) | `>=4.19.0 <7` |
| Browser | **Unsupported** — server SDK only; a project key must never reach a browser |
| Metrics / logs export | Not implemented (traces only) |

## Dependency family (research summary, resolved 2026-07)

One internally compatible OpenTelemetry release train: stable **2.9.0** core +
its matched experimental **0.220.0** line (released together; mixing
generations is unsupported upstream).

| Package | Version | Status | Role |
| ------- | ------- | ------ | ---- |
| `@opentelemetry/api` | 1.9.1 (`^1.9.0`) | stable | tracing API, context, diag |
| `@opentelemetry/sdk-trace-node` | 2.9.0 | stable | NodeTracerProvider, BatchSpanProcessor |
| `@opentelemetry/resources` | 2.9.0 | stable | `defaultResource` + `resourceFromAttributes` |
| `@opentelemetry/core` | 2.9.0 | stable | W3C trace-context/baggage propagators |
| `@opentelemetry/context-async-hooks` | 2.9.0 | stable | AsyncLocalStorage context manager |
| `@opentelemetry/exporter-trace-otlp-proto` | 0.220.0 | experimental line | the OTLP/HTTP **protobuf** exporter (JSON exporter deliberately not used) |
| `@opentelemetry/instrumentation` | 0.220.0 | experimental line | `registerInstrumentations` |
| `@opentelemetry/instrumentation-openai` | 0.18.0 | **optional peer** | official OpenAI instrumentation (semconv 1.36 chat / 1.38 responses) |
| `@opentelemetry/auto-instrumentations-node` | 0.78.0 | **optional peer** | official Node bundle (`fs` excluded upstream by default) |

`@opentelemetry/sdk-node` (0.220.0) was considered and not used: it bundles
metrics/logs wiring Helios does not need and is itself on the experimental
line; owning a `NodeTracerProvider` directly keeps the dependency surface
smaller and the lifecycle explicit. The two instrumentation bundles are
**optional peer dependencies** so the base install stays lean; enabling
`instrumentations.node`/`instrumentations.openai` without installing them
produces a clear `HeliosInstrumentationError` with the install command.

## Cross-language consistency with the Python SDK

Shared: environment variables (`HELIOS_API_KEY`, `HELIOS_ENDPOINT`,
`HELIOS_SERVICE_NAME`, `HELIOS_ENVIRONMENT`, `HELIOS_CAPTURE_CONTENT` +
`OTEL_SERVICE_NAME` fallback), endpoint normalization (base URL or full ingest
URL, no double-append), canonical `helios.span.type` values
(`agent`/`retrieval`/`tool`/`llm`/`custom`), GenAI attribute keys and
request→response model precedence, content capture off by default, idempotent
identical reconfigure / conflicting reconfigure error / reconfigure only after
shutdown.

Deliberate differences (not copied from Python):

- **Stricter endpoint security:** plain HTTP is allowed only for loopback
  hosts; non-loopback requires HTTPS or an explicit `allowInsecureHttp: true`.
- **API-key shape validation:** keys must look like `hel_proj_…` (rejected
  without echoing the value).
- **Provider ownership:** OTel JS 2.x removed `addSpanProcessor`, so the SDK
  never attaches to an existing provider; it owns one and refuses to replace a
  foreign global provider.
- **`Helios.trace()` is always a new root** (workflow semantics); nested agent
  spans use `Helios.span(..., { spanType: "agent" })`.
- Attribute normalization drops invalid values instead of stringifying
  arbitrary objects (prevents accidental content leaks).

## Endpoint, authentication, environment

- Route: `POST {endpoint}/v1/otlp/traces`, `Content-Type:
  application/x-protobuf`, `Authorization: Bearer hel_proj_…` (scope
  `traces:ingest`; reads in the integration suite use `traces:read`).
- Credentials never go into URLs, diagnostics, exports, or error messages.
- `environment` becomes the `deployment.environment.name` resource attribute
  (the backend also accepts an `x-helios-environment` header as a fallback for
  raw OTLP clients; the SDK uses the resource attribute, like Python).
- Resource attributes: `service.name`, optional `service.version`,
  optional `deployment.environment.name`, `helios.sdk.name`/`.version`, plus
  OTel defaults (`telemetry.sdk.*`). User `resourceAttributes` are validated:
  capped (32 keys / 256 chars), secret-like keys rejected, SDK-managed keys
  protected. No hostname/process/env collection beyond OTel defaults.

## Privacy boundary

- No prompt, completion, tool argument/result, or document content by default
  — the OpenAI instrumentation's `captureMessageContent` is forced to the
  Helios-resolved value **after construction**, so the upstream
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` env var cannot
  silently enable capture (verified by test).
- Opt-in is explicit: `captureContent: true` or `HELIOS_CAPTURE_CONTENT=true`.
- Diagnostics are off by default; when enabled, output is redacted
  (`hel_proj_…`, bearer values, `sk-…` shapes, JWTs) and exporter payloads are
  never logged.
- The OTLP exporter's own HTTP requests are not self-traced (verified: no
  `traceparent` injection on exporter POSTs with `node: true`).

## Testing and CI

- `npm test` — 74 `node --test` unit tests (compiled CommonJS so
  require-in-the-middle instrumentation patching is exercised the way real
  Node CJS apps experience it): configuration/env/endpoint validation, span
  semantics and async context, error recording, export headers/route/payload,
  failure absorption, diagnostics redaction, fake-OpenAI instrumentation
  (local server, no external network), Node http instrumentation, defaults-off
  checks.
- `npm run verify:package` — build, `npm pack`, packed-file allowlist
  (`package.json` + `README.md` + `dist/` only), artifact secret scan, version
  consistency, then installs the tarball into temp fixtures and runs **ESM**,
  **CommonJS**, and **TypeScript** consumers on plain Node.
- `npm run integration:backend` — real local FastAPI + isolated test Postgres:
  creates a project + scoped key, exports a five-span workflow
  (root/retrieval/llm/tool/error) through the **packed** SDK, verifies
  hierarchy, service/environment metadata, span types, model precedence,
  numeric tokens, error status, project isolation (second project's key →
  404), content/credential exclusion, then revokes the key and confirms
  read/export return 401 while the app keeps running. Cleans up after itself.
- CI job **TypeScript SDK** runs all of the above on Node 20 with a Postgres
  service. No npm token, no provider secret, no external OpenAI request.

## Import order and known limitations

- Call `Helios.configure()` **before** importing instrumented libraries.
  CommonJS resolution of instrumented libraries is the tested path; pure-ESM
  loader hooks (`import-in-the-middle`) are not configured by this SDK.
- After `shutdown()`, already-imported libraries cannot be re-instrumented in
  the same process (upstream patching limitation) — restart the process.
- `@opentelemetry/instrumentation-http` 0.220.x emits the legacy HTTP
  semantic conventions by default (`http.method` etc.).
- Serverless: `await Helios.forceFlush()` before the handler returns.
- Traces only — no metrics or logs export, no cost computation, no
  quality/hallucination claims.

## Examples

- [`examples/typescript-basic/`](../examples/typescript-basic/) — manual
  workflow + retrieval/tool/LLM spans, flush/shutdown (no provider calls).
- [`examples/typescript-openai/`](../examples/typescript-openai/) — official
  OpenAI instrumentation with correct startup ordering; requires the user's
  own `OPENAI_API_KEY` locally and never runs in CI.

## Migrating from raw OpenTelemetry configuration

Replace manual `NodeTracerProvider` + `OTLPTraceExporter` + header wiring with
`Helios.configure(...)`; keep using the OTel API anywhere you already do —
`Helios.getTracer()` returns a normal `Tracer`, `Helios.getActiveSpan()` the
active span, and spans created by other OTel libraries nest correctly since
the SDK registers the standard global provider, AsyncLocalStorage context
manager, and W3C propagators.

## Remaining before npm publication

License selection (package is currently `UNLICENSED`), org/npm scope
ownership for `@helios-ai`, changelog + semver policy (recommend staying
`0.x` until the OTel experimental exporter line stabilizes), provenance
signing, and a decision on ESM loader-hook support for pure-ESM
instrumentation consumers.
