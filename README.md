# Helios

Observability platform for tracing, evaluating, and debugging LLM applications, agents, and RAG pipelines.

**Portfolio MVP**: a full-stack prototype demonstrating real backend integration, not a production SaaS. What works today: FastAPI read/write APIs, PostgreSQL persistence, Python SDK trace ingestion, and live frontend-backend wiring. Some create/run actions in the UI are demo-only placeholders.

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
  <a href="https://www.loom.com/share/cd168cff3de843e8a0c00a1980085992">
  </a>
</p>

### What's real in this MVP

| Layer        | Implemented                                                           |
| ------------ | --------------------------------------------------------------------- |
| **Backend**  | FastAPI, SQLAlchemy, Alembic, trace ingestion + analytics read APIs   |
| **Database** | PostgreSQL: traces, spans, projects, seeded eval/RAG data             |
| **SDK**      | Python client submitting nested spans via `POST /v1/traces`           |
| **Frontend** | Live API mode with demo fallback; dashboard, traces, RAG, evals wired |
| **Not yet**  | Auth, workers, prompt/dataset/eval creation flows, OpenTelemetry      |

---

## Features

- **Trace visualization**: nested span trees for LLM, RAG, tool, and agent steps
- **RAG analytics**: retrieval hit rate, citation coverage, chunk quality, missed queries
- **Evaluations**: eval run summaries and model comparison tables
- **Prompt tracking**: prompt version scores, latency, and cost
- **Dataset metrics**: dataset summaries derived from eval runs
- **Python SDK**: lightweight client for `POST /v1/traces` ingestion
- **External demo app**: deterministic RAG support bot that submits real traces

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

Helios separates **ingestion** (SDK → API → Postgres) from **read APIs** (dashboard, traces, RAG, evals) consumed by the React console. Demo fallback keeps the UI usable when the backend is offline.

**Diagrams:** [diagrams/component.md](diagrams/component.md) · [diagrams/trace-lifecycle.md](diagrams/trace-lifecycle.md) · [diagrams/deployment.md](diagrams/deployment.md) · [diagrams/production-deployment.md](diagrams/production-deployment.md)

**Docs:**

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): components, flows, tradeoffs
- [docs/SDK_INGESTION.md](docs/SDK_INGESTION.md): SDK install and RAG demo
- [docs/BACKEND_PLAN.md](docs/BACKEND_PLAN.md): phased backend roadmap
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): Render + Vercel deployment guide

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
python -m venv .venv-demo && source .venv-demo/bin/activate
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

### Demo app (SDK ingestion)

From repo root with `.venv-demo` activated:

```bash
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

## Deployment

Recommended **free-tier** path for a public portfolio demo:

| Layer    | Platform                          | URL (after deploy)             |
| -------- | --------------------------------- | ------------------------------ |
| Frontend | Vercel                            | `https://<frontend-url>`       |
| Backend  | Render Web Service                | `https://<render-backend-url>` |
| Database | Render Postgres (Supabase backup) | via `DATABASE_URL`             |

Full step-by-step instructions, env var matrix, seed commands, and CORS troubleshooting: **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)**.

Quick production settings:

- **Vercel (build-time):** `VITE_API_BASE_URL=https://<render-backend-url>`, `VITE_HELIOS_DEMO_MODE=false`
- **Render (runtime):** `DATABASE_URL`, `CORS_ORIGINS=http://localhost:5173,https://<frontend-url>`, `HELIOS_DEMO_MODE=true` until seeded, then `false`

Free Render web services may sleep when idle; expect cold starts on the first request after inactivity.

---

## Limitations

- **Portfolio MVP**: sample-scale metrics, not production volume or multi-tenant ops
- **No auth**: local dev APIs are open; no API keys yet
- **Lightweight SDK**: not OpenTelemetry; no batching or retries
- **Simulated RAG demo app**: keyword search + deterministic LLM responses; no paid API keys
- **Demo-only UI actions**: New prompt, New dataset, Run evaluation, New experiment open a placeholder notice; no create flows yet
- **Static panels**: some trace detail side content remains demo placeholders
- **No workers**: eval execution and async pipelines are not implemented

---

## Future improvements

- API key auth and project-scoped ingestion
- TypeScript SDK and OpenTelemetry exporter
- Eval runner with background workers
- Prompt/dataset/eval creation workflows
- CI/CD and production monitoring
- Loom walkthrough video ([docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md))

See [docs/PROJECT_IMPROVEMENTS.md](docs/PROJECT_IMPROVEMENTS.md).

---

## Disclaimer

Helios is a **portfolio project** built to demonstrate full-stack AI observability engineering: real FastAPI backend, PostgreSQL persistence, SDK ingestion, and frontend integration. Demo metrics and seeded data are illustrative. No production deployments, customer claims, or compliance certifications are implied.
