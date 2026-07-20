# TypeScript SDK — basic quickstart (Node)

Exports one root workflow trace with nested retrieval / tool / LLM spans to a
running Helios backend through the canonical OTLP/HTTP protobuf path, then
force-flushes and shuts down.

The `@helios-ai/sdk` package is **not published to npm**; this example installs
it from the repository workspace (`file:../../sdk/typescript`).

## Setup

```bash
# 1. Build the SDK once (from repo root)
cd sdk/typescript && npm install && npm run build && cd ../..

# 2. Install the example's dependency (resolves to the local package)
cd examples/typescript-basic
npm install

# 3. Configure (mint a key in /app/getting-started or via the admin CLI)
export HELIOS_API_KEY=<YOUR_HELIOS_PROJECT_KEY>   # never commit it
export HELIOS_ENDPOINT=http://localhost:8000
export HELIOS_SERVICE_NAME=ts-basic-example

# 4. Run
npm start
```

Then open **Traces** in the Helios console: you should see a
`support.workflow` trace with `retrieval.search`, `tool.lookup_policy`, and
`chat gpt-4o-mini` children (model + token attributes, no content).

Notes

- Requires Node `^18.19.0 || >=20.6.0`.
- The LLM span here sets metadata explicitly — no OpenAI request is made.
  For automatic OpenAI tracing see `../typescript-openai`.
- `forceFlush()`/`shutdown()` matter: spans are batched and a process that
  exits immediately would drop them.
