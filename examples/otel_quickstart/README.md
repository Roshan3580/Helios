# OTel Quickstart

Sends a small nested trace (agent → retrieval → LLM → tool) to Helios's
canonical v2 ingestion endpoint using the **official OpenTelemetry Python SDK**
and the **OTLP/HTTP protobuf exporter**. Deterministic; no LLM API key needed.

The project is identified by the temporary `X-Helios-Project-Slug` header
(replaced by project API keys in a later batch).

## Setup (from repo root)

```bash
python3 -m venv examples/otel_quickstart/.venv
source examples/otel_quickstart/.venv/bin/activate
pip install -r examples/otel_quickstart/requirements.txt
```

## Run against a local backend

Backend must be running with migration `002_otel_foundation` applied
(see repo README "Run locally").

```bash
python examples/otel_quickstart/main.py \
  --api-url http://localhost:8000 \
  --project-slug otel-quickstart
```

The script prints the emitted 32-hex `trace_id`. Verify via the v2 read APIs:

```bash
curl "http://localhost:8000/v2/traces?project_slug=otel-quickstart"
curl "http://localhost:8000/v2/traces/<trace_id>?project_slug=otel-quickstart"
```

Expected: one trace for `service.name=otel-quickstart-agent` with 4 spans
(`agent.answer_question` root, `retriever.search`, `llm.generate` with
`gen_ai.*` attributes and a completion event, `tool.lookup_policy`).
