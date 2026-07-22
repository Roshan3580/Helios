# TypeScript SDK — official OpenAI auto-instrumentation (Node)

Traces real OpenAI chat-completion calls automatically through the **official**
`@opentelemetry/instrumentation-openai` package, exporting model and token
telemetry (never prompt/completion content) to Helios.

The `@helios-ai/sdk` package is **not published to npm**; this example installs
it from the repository workspace (`file:../../sdk/typescript`).

> **This example makes one real OpenAI API request** when you run it with your
> own `OPENAI_API_KEY`. It never runs in CI, and no key is committed anywhere.

## Setup

```bash
# 1. Build the SDK once (from repo root)
cd sdk/typescript && npm install && npm run build && cd ../..

# 2. Install the example's dependencies (SDK + openai + official instrumentation)
cd examples/typescript-openai
npm install

# 3. Configure — two SEPARATE credentials:
export HELIOS_API_KEY=<YOUR_HELIOS_PROJECT_KEY>   # Helios ingestion (hel_proj_…)
export HELIOS_ENDPOINT=http://localhost:8000
export OPENAI_API_KEY=<YOUR_OPENAI_KEY>           # OpenAI only; Helios never sees it

# 4. Run
npm start
```

Open **Traces** in the Helios console: the `openai.workflow` trace contains a
`chat gpt-4o-mini` child span created by the official instrumentation with
`gen_ai.request.model`, `gen_ai.response.model`, and numeric
`gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`.

## Startup ordering (important)

`Helios.configure({ instrumentations: { openai: true } })` must complete
**before** the `openai` module is loaded — instrumentation patches modules as
they are required. The example is CommonJS and requires `openai` after
configure; pure-ESM apps would additionally need OpenTelemetry's ESM loader
hooks, which this SDK does not configure (CommonJS is the tested path).

## Privacy

- Content capture is **off by default**: prompts, completions, and tool
  arguments never reach Helios. Only model identity, token counts, finish
  reasons, and response IDs are exported.
- The SDK keeps this default even if
  `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true` is set; opting in
  requires `captureContent: true` in `Helios.configure` (or
  `HELIOS_CAPTURE_CONTENT=true`).
- Your `OPENAI_API_KEY` is read only by the OpenAI client; it is never sent to
  Helios or included in spans.

Supported `openai` package range: `>=4.19.0 <7` (the official
instrumentation's supported window).
