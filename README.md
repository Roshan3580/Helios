# Helios

Observability platform for tracing, evaluating, and debugging LLM applications, agents, and RAG pipelines.

```mermaid
flowchart TB
    subgraph External["External App"]
        App["RAG Support Bot"]
    end
    subgraph SDK["Python SDK"]
        Client["helios_sdk"]
    end
    subgraph Backend["FastAPI"]
        Ingest["POST /v1/traces"]
        Read["Dashboard & Analytics APIs"]
    end
    subgraph Data["PostgreSQL"]
        DB["Traces · Spans · Projects"]
    end
    subgraph UI["Frontend"]
        Console["React Console"]
    end
    App --> Client --> Ingest --> DB
    Read --> DB
    Console --> Read
```

---

## Features

- **Trace visualization** — nested span trees for LLM, RAG, tool, and agent steps
- **RAG analytics** — retrieval hit rate, citation coverage, chunk quality, missed queries
- **Evaluations** — eval run summaries and model comparison tables
- **Prompt tracking** — prompt version scores, latency, and cost
- **Dataset metrics** — dataset summaries derived from eval runs
- **Python SDK** — lightweight client for `POST /v1/traces` ingestion
- **External demo app** — deterministic RAG support bot that submits real traces

---

## Screenshots

| Landing                                       | Dashboard                               | Traces                            |
| --------------------------------------------- | --------------------------------------- | --------------------------------- |
| ![Landing page](screenshots/landing-page.png) | ![Dashboard](screenshots/dashboard.png) | ![Traces](screenshots/traces.png) |

| Trace detail                                  | RAG analytics                                   | Evaluations                                 |
| --------------------------------------------- | ----------------------------------------------- | ------------------------------------------- |
| ![Trace detail](screenshots/trace-detail.png) | ![RAG analytics](screenshots/rag-analytics.png) | ![Evaluations](screenshots/evaluations.png) |

| Prompts                             | Datasets                              | SDK demo                              |
| ----------------------------------- | ------------------------------------- | ------------------------------------- |
| ![Prompts](screenshots/prompts.png) | ![Datasets](screenshots/datasets.png) | ![SDK demo](screenshots/sdk-demo.png) |

> Placeholder images — replace with real captures before recording. See [screenshots/README.md](screenshots/README.md).

---

## Architecture

Helios separates **ingestion** (SDK → API → Postgres) from **read APIs** (dashboard, traces, RAG, evals) consumed by the React console. Demo fallback keeps the UI usable when the backend is offline.

**Diagrams:** [diagrams/component.md](diagrams/component.md) · [diagrams/trace-lifecycle.md](diagrams/trace-lifecycle.md) · [diagrams/deployment.md](diagrams/deployment.md)

**Docs:**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — components, flows, tradeoffs
- [docs/SDK_INGESTION.md](docs/SDK_INGESTION.md) — SDK install and RAG demo
- [docs/BACKEND_PLAN.md](docs/BACKEND_PLAN.md) — phased backend roadmap

---

## Python SDK example

```python
from helios_sdk import HeliosClient

client = HeliosClient(
    base_url="http://localhost:8000",
    project_slug="rag-support-bot",
    project_name="RAG Support Bot",
    environment="development",
)

trace = client.create_trace(
    user_query="How do I rotate API keys without downtime?",
    app_name="rag-support-bot",
    model="gpt-4o-mini",
)

with trace.span("retriever.search", span_type="rag") as span:
    span.set_input("api key rotation policy")
    span.set_output("Retrieved 3 policy chunks")

with trace.span("llm.generate", span_type="llm", provider="openai", model="gpt-4o-mini") as span:
    span.set_tokens(1240)
    span.set_cost(0.0042)

client.submit_trace(trace)
```

---

## Demo flow

```
External RAG app  →  Python SDK  →  POST /v1/traces  →  PostgreSQL  →  Dashboard & /app/traces
```

Run the included demo from the repo root:

```bash
pip install -r examples/rag_support_bot/requirements.txt
python examples/rag_support_bot/run_demo.py --query "How do I rotate API keys without downtime?"
```

Each run prints a new `trc_...` ID and a link to `/app/traces/<trace_id>`.

---

## Tech stack

| Layer        | Stack                                                                          |
| ------------ | ------------------------------------------------------------------------------ |
| **Frontend** | React 19, TypeScript, TanStack Start/Router, Vite 8, Tailwind CSS 4, shadcn/ui |
| **Backend**  | FastAPI, SQLAlchemy 2.x, Alembic, Pydantic                                     |
| **Database** | PostgreSQL 16                                                                  |
| **SDK**      | Python 3.10+, httpx (`helios_sdk`)                                             |

---

## Running locally

### Frontend

```bash
bun install
cp .env.example .env   # set VITE_HELIOS_DEMO_MODE=false for live API
bun dev
```

### Backend

```bash
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
alembic upgrade head
uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/v1/demo/seed
```

### Demo app (SDK ingestion)

```bash
python -m venv .venv-demo && source .venv-demo/bin/activate
pip install -r examples/rag_support_bot/requirements.txt
python examples/rag_support_bot/run_demo.py --query "How do I rotate API keys without downtime?"
```

### Scripts

| Command             | Description         |
| ------------------- | ------------------- |
| `bun run dev`       | Frontend dev server |
| `bun run build`     | Production build    |
| `bun run lint`      | ESLint              |
| `bun run typecheck` | TypeScript check    |

---

## Limitations

- **Portfolio / demo scope** — sample data and small trace volumes, not production scale
- **No auth** — ingestion and read APIs are open in local dev
- **Lightweight SDK** — not OpenTelemetry; no batching or retries
- **Simulated RAG demo** — keyword search + fake LLM, no paid API keys
- **Static UI panels** — some trace detail side content remains demo placeholders
- **No workers** — eval execution and async pipelines are not implemented

---

## Future improvements

- API key auth and project-scoped ingestion
- TypeScript SDK and OpenTelemetry exporter
- Eval runner with background workers
- Prompt CRUD and immutable version history
- CI/CD, deployment guide, and production monitoring
- Replace screenshot placeholders with live captures

See [docs/PROJECT_IMPROVEMENTS.md](docs/PROJECT_IMPROVEMENTS.md) and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

---

## Disclaimer

Helios is a **portfolio project** built to demonstrate full-stack AI observability engineering. Demo metrics and seeded data are illustrative. No production deployments, customer claims, or compliance certifications are implied.
