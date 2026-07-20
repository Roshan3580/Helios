# @helios-ai/sdk

Helios OpenTelemetry SDK for **Node.js servers**: canonical OTLP/HTTP protobuf
trace export to Helios with project API-key authentication, typed manual
tracing helpers, GenAI attribute builders, and optional official OpenTelemetry
auto-instrumentation.

> **Publication status:** the package name `@helios-ai/sdk` is reserved for
> publication but has **not been published to npm**. Install it from the
> repository artifact (below). Do not run `npm install @helios-ai/sdk` against
> the public registry yet.

> **Node server SDK only.** Browser usage is unsupported: the SDK reads
> environment variables, uses Node `http(s)` export, async-hooks context, and
> would expose your project API key if bundled for the browser. Never ship a
> `hel_proj_…` key to a browser.

## Requirements

- **Node.js** `^18.19.0 || >=20.6.0` (the OpenTelemetry JS SDK 2.x support
  window)
- **TypeScript** ≥ 5.0 for TypeScript consumers (developed against 5.9;
  plain-JavaScript usage needs no TypeScript)
- OpenAI instrumentation (optional) supports `openai` `>=4.19.0 <7`

## Install (from the repository artifact)

```bash
# from a Helios checkout
cd sdk/typescript
npm install
npm run build
npm pack        # produces helios-ai-sdk-0.1.0.tgz

# in your application
npm install /path/to/helios-ai-sdk-0.1.0.tgz
```

Both ESM (`import`) and CommonJS (`require`) entry points ship with TypeScript
declarations; both are exercised by the package verification suite.

## Quickstart

```ts
import { Helios } from "@helios-ai/sdk";

await Helios.configure({
  apiKey: process.env.HELIOS_API_KEY!,     // hel_proj_… (scope: traces:ingest)
  endpoint: process.env.HELIOS_ENDPOINT!,  // e.g. https://your-helios-backend
  serviceName: "support-agent",
  environment: "development",
});

await Helios.trace("support.workflow", async () => {
  await Helios.span(
    "retrieval.search",
    { spanType: "retrieval", attributes: { "retrieval.document_count": 4 } },
    async () => {
      /* nested operation */
    },
  );
});

await Helios.forceFlush();
await Helios.shutdown();
```

### Environment variables

| Variable | Meaning |
| -------- | ------- |
| `HELIOS_API_KEY` | Project API key (required unless passed explicitly) |
| `HELIOS_ENDPOINT` | Base URL or full `/v1/otlp/traces` URL (default `http://localhost:8000`) |
| `HELIOS_SERVICE_NAME` | `service.name` (falls back to `OTEL_SERVICE_NAME`) |
| `HELIOS_SERVICE_VERSION` | Optional `service.version` |
| `HELIOS_ENVIRONMENT` | Optional `deployment.environment.name` |
| `HELIOS_CAPTURE_CONTENT` | Opt-in GenAI content capture (default `false`) |

Explicit options always win over environment variables.

### Endpoint and authentication

- Canonical route: `POST {endpoint}/v1/otlp/traces`, OTLP/HTTP **protobuf**.
- Authentication is `Authorization: Bearer hel_proj_…` — attached internally,
  never placed in the URL, never logged.
- Plain HTTP is allowed only for loopback endpoints; non-loopback endpoints
  require HTTPS unless `allowInsecureHttp: true` is set (development only).
- Passing the full ingest URL is fine; the path is never double-appended.

### Manual tracing

- `Helios.trace(name, [options], fn)` — starts a **new root** workflow trace
  (span type `agent` by default).
- `Helios.span(name, [options], fn)` — nests under the active span (or starts
  a root when none is active). `options.spanType` accepts the canonical Helios
  values: `agent`, `retrieval`, `tool`, `llm`, `custom`.
- Callbacks may be sync or async; the return value is preserved; thrown
  errors/rejections are recorded (`exception` event + `ERROR` status), the
  span always ends exactly once, and the original error is rethrown.
- `Helios.getActiveSpan()` / `Helios.getTracer()` expose the raw OTel API.

### AI attribute builders

```ts
import { llmAttributes, toolAttributes, retrievalAttributes, workflowAttributes } from "@helios-ai/sdk";

llmAttributes({ operation: "chat", requestModel: "gpt-4o-mini", inputTokens: 42, outputTokens: 7 });
toolAttributes({ toolName: "kb.search" });
retrievalAttributes({ operation: "search", documentCount: 4, source: "vector-store" });
workflowAttributes({ agentName: "support-agent", stepName: "triage" });
```

Builders emit OpenTelemetry GenAI semantic-convention keys the Helios backend
already reads (`gen_ai.request.model` → `gen_ai.response.model` precedence,
numeric `gen_ai.usage.input_tokens`/`output_tokens`). Token counts must be
finite non-negative numbers — malformed values are omitted, never estimated.
No cost fields, prompts, completions, tool arguments/results, or document
content are ever produced.

### Optional instrumentation (disabled by default)

```ts
await Helios.configure({
  // ...
  instrumentations: {
    openai: true, // official @opentelemetry/instrumentation-openai
    node: true,   // official @opentelemetry/auto-instrumentations-node
  },
});
```

Both are **optional peer dependencies** — install the ones you enable:

```bash
npm install @opentelemetry/instrumentation-openai       # for openai: true
npm install @opentelemetry/auto-instrumentations-node   # for node: true
```

**Import order matters.** Instrumentation patches modules when they are
required, so call `Helios.configure()` **before** importing/constructing the
libraries you want traced (e.g. `openai`). In CommonJS apps, use a dynamic
`require`/`import()` after configure; in ESM apps additionally note that
loader-based ESM patching is not configured by this SDK — CommonJS resolution
of the instrumented library (the `openai` package's default in Node) is the
tested path. After `Helios.shutdown()`, already-imported libraries cannot be
re-instrumented in the same process (upstream patching limitation) — restart
the process to re-enable instrumentation.

**Content privacy.** The OpenAI instrumentation never captures prompt or
completion content unless you explicitly set `captureContent: true` (or
`HELIOS_CAPTURE_CONTENT=true`). The SDK forces this default even when the
upstream `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` env var is set.
Model names, token counts, finish reasons, and response IDs are captured;
message text, tool arguments/results, and API keys are not. The Helios OTLP
exporter's own requests are never self-traced (verified by test).

`instrumentations: { node: { disabledInstrumentations: ["@opentelemetry/instrumentation-dns"] } }`
turns off individual noisy instrumentations; `@opentelemetry/instrumentation-fs`
is excluded upstream by default.

### Lifecycle

- `Helios.configure()` — async; loads optional instrumentation, registers the
  tracer provider, context manager (AsyncLocalStorage), and W3C propagators.
  Identical repeated configuration is idempotent; conflicting reconfiguration
  throws `HeliosConfigurationError`; reconfiguration is allowed after
  `shutdown()`. A foreign global tracer provider is never replaced.
- `Helios.isConfigured()` / `Helios.getTracer()`
- `Helios.forceFlush()` — drains pending spans; absorbs routine export
  failures instead of throwing into application code.
- `Helios.shutdown()` — flush + release global registrations; idempotent.

**Serverless:** call `await Helios.forceFlush()` before the handler returns
(or `shutdown()` if the instance is being frozen); batching is timer-based and
a frozen sandbox will otherwise drop spans.

### Failure behavior

- Configuration problems (missing/malformed key, bad endpoint, conflicting
  reconfigure) throw `HeliosConfigurationError` — messages never include the
  key value.
- Missing optional instrumentation peers throw `HeliosInstrumentationError`
  with the install command.
- Runtime export failures (backend down, 5xx) never crash the application:
  spans are dropped via normal OpenTelemetry exporter behavior and surfaced
  only through opt-in diagnostics.

### Diagnostics

Silent by default. `diagnostics: "error" | "warn" | "info" | "debug"` enables
development troubleshooting through the OTel diag API with **redaction**:
`hel_proj_…` keys, bearer headers, provider-key-shaped strings, and JWTs are
masked; exporter payloads and message content are never logged.

### Differences from the Python SDK

- Same env vars, endpoint normalization, `helios.span.type` values, and
  content-off default.
- `Helios` is a module-level singleton facade (`Helios.configure()` returns
  `void`), not an instance.
- `Helios.trace()` always starts a new root trace; Python's `helios.agent()`
  nests. Use `Helios.span(..., { spanType: "agent" })` for a nested agent span.
- The Node SDK always owns its provider; it does not attach to a pre-existing
  SDK provider (OTel JS 2.x removed `addSpanProcessor`). It refuses to replace
  a foreign global provider instead.

## Development

```bash
npm install
npm run typecheck
npm test                  # node --test (compiled CJS)
npm run build             # dist/esm + dist/cjs + declarations
npm run verify:package    # pack + allowlist + ESM/CJS/TS consumer smokes
npm run integration:backend  # real local Helios backend round-trip
```
