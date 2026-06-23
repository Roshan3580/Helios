# Helios

AI systems observability platform for tracing, evaluating, and debugging production LLM applications.

## Current status

**Frontend complete; backend and Phase 3 analytics APIs shipped. Phase 4 adds Python SDK trace ingestion.**

Helios ships a visually complete frontend with demo fallback. A FastAPI backend with PostgreSQL, trace ingestion, analytics read APIs, and a lightweight Python SDK is available for local development.

## Why this project exists

Production LLM applications — agents, RAG pipelines, and multi-step workflows — are difficult to debug with traditional APM tools. Helios is designed to give developers a dedicated observability layer for AI systems: nested trace trees, prompt versioning, evaluation suites, RAG quality metrics, and cost/latency monitoring in one console.

## Product preview

Screenshots will be added to `screenshots/` as the product matures.

<!-- TODO: Add landing page and dashboard screenshots -->

## Core product modules

| Module                          | Description                                                                                  |
| ------------------------------- | -------------------------------------------------------------------------------------------- |
| **Traces**                      | Capture LLM calls, tool invocations, retrievers, and agent steps as nested span trees        |
| **Prompt Versions**             | Version prompts as first-class artifacts; diff outputs, scores, latency, and cost            |
| **Evaluations**                 | Run eval suites against fixed datasets with deterministic, LLM-as-judge, and code evaluators |
| **RAG Analytics**               | Monitor retrieval hit rate, citation coverage, and missing-source analysis                   |
| **Experiments**                 | Compare models, prompts, and configurations side by side                                     |
| **Cost and Latency Monitoring** | Aggregate token usage and spend by model, prompt, environment, and project                   |

## Planned backend architecture

```
Client SDK / OTel exporter
        │
        ▼
  Ingestion API (FastAPI)
        │
   ┌────┴────┐
   ▼         ▼
PostgreSQL  Redis (queues)
   │
   ▼
Eval workers · RAG analytics · Experiment runner
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/BACKEND_PLAN.md](docs/BACKEND_PLAN.md) for details.

## Tech stack

**Frontend (current)**

- React 19 + TypeScript
- TanStack Start / TanStack Router
- Vite 8
- Tailwind CSS 4
- Radix UI + shadcn/ui components
- Recharts

**Backend (Phase 1 foundation)**

- FastAPI, PostgreSQL, SQLAlchemy 2.x, Alembic, Pydantic
- Trace/project APIs and demo seed endpoint
- Redis, Celery/RQ — planned for later phases

## Local development

### Prerequisites

- Node.js ≥ 22.12 (recommended for TanStack Start)
- Bun or npm

### Setup

```bash
# Install dependencies
bun install   # or: npm install

# Copy environment template
cp .env.example .env

# Start dev server
bun dev       # or: npm run dev
```

### Scripts

| Script      | Description              |
| ----------- | ------------------------ |
| `dev`       | Start Vite dev server    |
| `build`     | Production build         |
| `preview`   | Preview production build |
| `lint`      | Run ESLint               |
| `format`    | Run Prettier             |
| `typecheck` | TypeScript check (`tsc`) |

### Backend (local)

```bash
docker compose -f docker-compose.dev.yml up --build
curl -X POST http://localhost:8000/v1/demo/seed
```

See [backend/README.md](backend/README.md) for API details.
See [docs/FRONTEND_BACKEND_INTEGRATION.md](docs/FRONTEND_BACKEND_INTEGRATION.md) for frontend ↔ backend wiring.
See [docs/SDK_INGESTION.md](docs/SDK_INGESTION.md) for Python SDK and external RAG demo.

### SDK + external trace demo

```bash
# Backend running on :8000, then:
cd sdk/python && pip install -e .
cd examples/rag_support_bot && pip install -r requirements.txt
python run_demo.py --query "How do I rotate API keys without downtime?"
```

## Roadmap

1. **Backend foundation** — API, database schema, trace ingestion
2. **Trace detail integration** — Connect frontend to live trace data
3. **Analytics read APIs** — Dashboard, RAG, evals, prompts, datasets
4. **SDK ingestion** — Python SDK + external RAG demo app
5. **Eval runner** — Dataset management and eval execution
6. **Prompt versioning** — CRUD, diff, and version history
7. **Auth and deployment** — Multi-tenant projects, production hosting

See [docs/PROJECT_IMPROVEMENTS.md](docs/PROJECT_IMPROVEMENTS.md) for prioritized backlog.

## Disclaimer

Helios is under active development. Demo data in the frontend is illustrative only. No production backend, customer deployments, or live metrics are claimed at this stage.
