# OTel Quickstart

Sends a small nested trace (agent → retrieval → LLM → tool) to Helios's
canonical v2 ingestion endpoint using the **official OpenTelemetry Python SDK**
and the **OTLP/HTTP protobuf exporter**. Deterministic; no LLM API key needed.

Authentication is a **project API key** sent as `Authorization: Bearer <key>`.
The key determines the project — no slug is sent. The key is a secret: never
commit it or place it in browser code. See
[docs/ADR_002_PROJECT_API_KEYS.md](../../docs/ADR_002_PROJECT_API_KEYS.md).

## Setup (from repo root)

```bash
python3 -m venv examples/otel_quickstart/.venv
source examples/otel_quickstart/.venv/bin/activate
pip install -r examples/otel_quickstart/requirements.txt
```

## Create a key and export it

Backend must have migration `003_project_api_keys` applied (see repo README).
From `backend/` (with `DATABASE_URL` set and its venv active):

```bash
python -m app.cli.api_keys create \
  --project-slug otel-quickstart \
  --project-name "OTel Quickstart" \
  --environment development \
  --name "Local development" \
  --scopes traces:ingest,traces:read
```

Copy the key printed once and export it:

```bash
export HELIOS_API_KEY=hel_proj_xxxxxxxxxxxxxxxx_...
```

## Run against a local backend

```bash
python examples/otel_quickstart/main.py --api-url http://localhost:8000
```

The script prints the emitted 32-hex `trace_id` (never the key). Verify via the
v2 read APIs using the same key:

```bash
curl -H "Authorization: Bearer $HELIOS_API_KEY" "http://localhost:8000/v2/traces"
curl -H "Authorization: Bearer $HELIOS_API_KEY" "http://localhost:8000/v2/traces/<trace_id>"
```

Expected: one trace for `service.name=otel-quickstart-agent` with 4 spans
(`agent.answer_question` root, `retriever.search`, `llm.generate` with
`gen_ai.*` attributes and a completion event, `tool.lookup_policy`).
