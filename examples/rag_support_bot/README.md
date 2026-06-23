# RAG Support Bot — Helios SDK Demo

Deterministic sample app that simulates a RAG support bot and submits a trace to Helios via the Python SDK. **No external API keys required.**

## What it does

1. Accepts a user query (CLI)
2. Runs keyword retrieval over a local fake knowledge base
3. Reranks chunks with a simple heuristic
4. Simulates LLM answer generation (no real model call)
5. Submits a nested trace with spans to `POST /v1/traces`

## Prerequisites

- Helios backend running at `http://localhost:8000`
- Python 3.10+

## Setup (from repo root)

```bash
# Start backend
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
uvicorn app.main:app --reload --port 8000

# Install demo + SDK (from repo root)
python -m venv .venv-demo
source .venv-demo/bin/activate
pip install -r examples/rag_support_bot/requirements.txt
```

## Run (from repo root)

```bash
python examples/rag_support_bot/run_demo.py \
  --query "How do I rotate API keys without downtime?" \
  --api-url http://localhost:8000
```

Sample queries:

- `How do I rotate API keys without downtime?`
- `Can I export traces to Datadog?`
- `Why did my RAG answer miss a citation?`

## Expected output

```
Helios RAG Support Bot demo
  backend:  http://localhost:8000
  query:    How do I rotate API keys without downtime?

Trace submitted successfully
  trace_id:   trc_a1b2c3
  spans:      6
  backend:    http://localhost:8000
  view trace: http://localhost:5173/app/traces/trc_a1b2c3
```

Each run generates a new `trc_...` ID. Reusing the same ID will fail.

## View in Helios UI

1. Set `VITE_HELIOS_DEMO_MODE=false` in `.env`
2. Run `bun dev`
3. Open the printed `/app/traces/<trace_id>` link

The trace also appears in `/app/traces` and updates dashboard aggregates.

## Honest limitations

- Retrieval and LLM steps are **simulated** — no OpenAI/Anthropic calls
- Knowledge base is a tiny in-memory sample
- No auth on ingestion yet
- This proves external trace submission, not production-scale ingestion
