# Helios

AI observability platform for tracing, evaluating, and debugging LLM applications, agents, and RAG pipelines.

**Live Demo:** [https://helios-alpha-nine.vercel.app/](https://helios-alpha-nine.vercel.app/)

Helios ships as a deployed full-stack system: a TanStack Start console on Vercel, a FastAPI backend on Render, PostgreSQL persistence, read APIs for dashboard and analytics views, and a Python SDK that ingests nested traces via `POST /v1/traces`.

## Demo

<div align="center">
  <a href="https://www.loom.com/share/cd168cff3de843e8a0c00a1980085992">
    <img
      style="max-width:900px;"
      src="https://cdn.loom.com/sessions/thumbnails/cd168cff3de843e8a0c00a1980085992-ed903f21e01f44d3-full-play.gif#t=0.1"
      alt="Helios Tracing for LLM and RAG Apps">
  </a>
</div>

<p align="center">
  <a href="https://www.loom.com/share/cd168cff3de843e8a0c00a1980085992">Watch the 90-second walkthrough</a>
</p>

---

## What it does

- **Trace ingestion:** accept nested span trees from the Python SDK at `POST /v1/traces`
- **Trace and span inspection:** list, filter, and open trace detail with nested span timelines
- **Dashboard summaries:** aggregate latency, cost, token usage, and recent traces via `GET /v1/dashboard/summary`
- **RAG analytics:** chunk hit rates, citation coverage, and quality signals via `GET /v1/rag/metrics`
- **Evaluations:** eval run summaries and model comparison tables via `GET /v1/evaluations`
- **Prompt and dataset tracking:** prompt version metrics and dataset summaries derived from eval runs
- **SDK-based external submission:** the deterministic RAG support bot under `examples/rag_support_bot` submits real traces into the same backend the UI reads

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

---

## Architecture

Helios separates **ingestion** (SDK → API → Postgres) from **read APIs** (dashboard, traces, RAG, evals) consumed by the React console.

```
External RAG app  →  Python SDK  →  POST /v1/traces  →  PostgreSQL  →  Dashboard & /app/traces
```

**Diagrams:** [diagrams/component.md](diagrams/component.md) · [diagrams/trace-lifecycle.md](diagrams/trace-lifecycle.md) · [diagrams/deployment.md](diagrams/deployment.md) · [diagrams/production-deployment.md](diagrams/production-deployment.md)

**Docs:**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, flows, tradeoffs
- [docs/SDK_INGESTION.md](docs/SDK_INGESTION.md): SDK install and RAG demo
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Render + Vercel deployment guide
- [docs/BACKEND_PLAN.md](docs/BACKEND_PLAN.md): phased backend roadmap

---

## Tech stack

| Layer          | Stack                                                                   |
| -------------- | ----------------------------------------------------------------------- |
| **Frontend**   | TanStack Start, React 19, TypeScript, Vite 8, Tailwind CSS 4, shadcn/ui |
| **Backend**    | FastAPI, Python, SQLAlchemy 2.x, Alembic, Pydantic                      |
| **Database**   | PostgreSQL 16                                                           |
| **SDK/Demo**   | Python SDK (`sdk/python/helios_sdk`), external RAG support bot demo     |
| **Deployment** | Vercel (frontend), Render (backend + Postgres)                          |

---

## Run locally

### Frontend

```bash
bun install
cp .env.example .env   # set VITE_HELIOS_DEMO_MODE=false for live API
bun dev
```

Open http://localhost:5173

### Backend

```bash
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
alembic upgrade head
uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/v1/demo/seed
```

### Scripts

| Command             | Description         |
| ------------------- | ------------------- |
| `bun run dev`       | Frontend dev server |
| `bun run build`     | Production build    |
| `bun run lint`      | ESLint              |
| `bun run typecheck` | TypeScript check    |

---

## SDK demo

The RAG support bot under `examples/rag_support_bot` runs a deterministic retrieval + LLM simulation and submits a nested trace to Helios. No external model API keys required.

**Setup (from repo root):**

```bash
python -m venv .venv-demo && source .venv-demo/bin/activate
pip install -r examples/rag_support_bot/requirements.txt
```

**Run against local backend:**

```bash
python examples/rag_support_bot/run_demo.py \
  --query "How do I rotate API keys without downtime?" \
  --api-url http://localhost:8000
```

Each run prints a new `trc_...` ID. With the frontend in live API mode (`VITE_HELIOS_DEMO_MODE=false`), open `/app/traces/<trace_id>` to inspect the submitted span tree.

**Programmatic usage (`sdk/python/helios_sdk`):**

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

See [examples/rag_support_bot/README.md](examples/rag_support_bot/README.md) and [docs/SDK_INGESTION.md](docs/SDK_INGESTION.md) for full walkthrough.

---

## Deployment

| Layer    | Platform        | URL                                                                            |
| -------- | --------------- | ------------------------------------------------------------------------------ |
| Frontend | Vercel          | [https://helios-alpha-nine.vercel.app/](https://helios-alpha-nine.vercel.app/) |
| Backend  | Render          | FastAPI web service (see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md))             |
| Database | Render Postgres | via `DATABASE_URL`                                                             |

Production frontend build settings:

- `VITE_API_BASE_URL`: Render backend URL
- `VITE_HELIOS_DEMO_MODE=false`

Full setup, env vars, seed commands, and CORS notes: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

---

## Future improvements

- API key auth and project-scoped ingestion
- TypeScript SDK and OpenTelemetry exporter
- Eval runner with background workers
- Prompt, dataset, and eval creation workflows (create/run UI actions are placeholders today)
- CI/CD and production monitoring

See [docs/PROJECT_IMPROVEMENTS.md](docs/PROJECT_IMPROVEMENTS.md) and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).
