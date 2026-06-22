# Helios

AI systems observability platform for tracing, evaluating, and debugging production LLM applications.

## Current status

**Frontend prototype complete; backend implementation planned.**

Helios currently ships as a frontend-first prototype with demo data. The marketing landing page and observability app shell are implemented. Backend APIs, trace ingestion, and live data integration are planned but not yet built.

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

**Backend (planned)**

- FastAPI, PostgreSQL, Redis
- Celery or RQ for async jobs
- SQLAlchemy + Alembic
- OpenTelemetry-compatible trace model

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

| Script    | Description              |
| --------- | ------------------------ |
| `dev`     | Start Vite dev server    |
| `build`   | Production build         |
| `preview` | Preview production build |
| `lint`    | Run ESLint               |
| `format`  | Run Prettier             |

There is no `typecheck` script yet. TypeScript is checked at build time via Vite.

## Roadmap

1. **Backend foundation** — API, database schema, trace ingestion
2. **Trace detail integration** — Connect frontend to live trace data
3. **Eval runner** — Dataset management and eval execution
4. **Prompt versioning** — CRUD, diff, and version history
5. **RAG analytics pipeline** — Retrieval metrics from production traffic
6. **SDK** — Python and TypeScript client libraries
7. **Auth and deployment** — Multi-tenant projects, production hosting

See [docs/PROJECT_IMPROVEMENTS.md](docs/PROJECT_IMPROVEMENTS.md) for prioritized backlog.

## Disclaimer

Helios is under active development. Demo data in the frontend is illustrative only. No production backend, customer deployments, or live metrics are claimed at this stage.
