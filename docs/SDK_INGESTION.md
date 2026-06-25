# SDK Ingestion (Phase 4)

Helios can receive observability data from external applications via `POST /v1/traces`. Phase 4 adds a lightweight Python SDK and a deterministic RAG demo app to prove end-to-end ingestion.

## What is real vs simulated

| Component              | Real                           | Simulated                    |
| ---------------------- | ------------------------------ | ---------------------------- |
| Trace ingestion API    | Yes                            | :                            |
| PostgreSQL persistence | Yes                            | :                            |
| Frontend trace UI      | Yes                            | :                            |
| Python SDK HTTP client | Yes                            | :                            |
| RAG demo retrieval     | Keyword search over local docs | Not vector DB                |
| RAG demo LLM           | :                              | Deterministic text responses |
| Auth / API keys        | :                              | Not implemented yet          |
| OpenTelemetry          | :                              | Not implemented yet          |

## Architecture

```
examples/rag_support_bot/run_demo.py
        │
        ▼
sdk/python/helios_sdk (HeliosClient)
        │
        ▼
POST /v1/traces  →  PostgreSQL  →  GET /v1/traces  →  Frontend UI
```

## 1. Start the backend

```bash
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
export HELIOS_DEMO_MODE=true
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Optional: seed demo data for the `acme` project (separate from SDK traces):

```bash
curl -X POST http://localhost:8000/v1/demo/seed
```

## 2. Install the Python SDK and demo (from repo root)

```bash
python -m venv .venv-demo
source .venv-demo/bin/activate
pip install -r examples/rag_support_bot/requirements.txt
```

This installs the editable SDK (`./sdk/python`) and demo dependencies in one step.

## 3. Run the RAG support bot demo

```bash
python examples/rag_support_bot/run_demo.py \
  --query "How do I rotate API keys without downtime?" \
  --api-url http://localhost:8000
```

Expected spans in the submitted trace:

| Span                       | Type   |
| -------------------------- | ------ |
| `user.query`               | input  |
| `retriever.keyword_search` | rag    |
| `reranker.score_chunks`    | rag    |
| `llm.generate_answer`      | llm    |
| `tool.lookup_policy`       | tool   |
| `response.finalize`        | output |

## 4. Verify via API

```bash
curl "http://localhost:8000/v1/traces?project_slug=rag-support-bot&limit=5"
curl "http://localhost:8000/v1/traces/<trace_id>"
curl "http://localhost:8000/v1/dashboard/summary?project_slug=rag-support-bot"
```

## 5. View in the frontend

```bash
# From repo root
cp .env.example .env
# VITE_HELIOS_DEMO_MODE=false
# VITE_API_BASE_URL=http://localhost:8000
bun dev
```

Open:

- `/app/traces`: SDK trace appears in the list (may need to clear `project_slug=acme` filter if added later; currently lists all projects)
- `/app/traces/<trace_id>`: nested span timeline from backend
- `/app/dashboard`: aggregate counts update when live API mode is on

If the backend is stopped, pages fall back to demo data with the existing **Demo fallback** banner.

## SDK API summary

```python
from helios_sdk import HeliosClient

client = HeliosClient(
    base_url="http://localhost:8000",
    project_slug="rag-support-bot",
    project_name="RAG Support Bot",
    environment="development",
)

trace = client.create_trace(
    user_query="...",
    app_name="rag-support-bot",
    model="gpt-4o-mini",
)

with trace.span("retriever.search", span_type="rag") as span:
    span.set_input("...")
    span.set_output("...")
    span.set_metadata({"top_k": 3})

client.submit_trace(trace)
```

## Known limitations

- SDK is lightweight and portfolio-focused; not a full OTel SDK
- No ingestion auth or rate limits
- Trace detail side panels (retrieved chunks UI) may still show static demo content
- Dashboard metrics for SDK project are sample-scale
- Re-submitting the same `trace_id` will fail (IDs are unique per run)

## Next steps (future phases)

- API key auth per project
- TypeScript SDK
- OpenTelemetry exporter compatibility
- Async/batch ingestion
