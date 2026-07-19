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

- **OpenTelemetry ingestion (v2, canonical):** OTLP/HTTP protobuf at `POST /v1/otlp/traces`, project-key-authenticated reads at `GET /v2/traces` (`Authorization: Bearer <project-api-key>`) — see [docs/ADR_001_OTLP_TRACE_FOUNDATION.md](docs/ADR_001_OTLP_TRACE_FOUNDATION.md), [docs/ADR_002_PROJECT_API_KEYS.md](docs/ADR_002_PROJECT_API_KEYS.md), and [examples/otel_quickstart](examples/otel_quickstart/)
- **Python instrumentation SDK (v2):** `Helios.configure(...)` exports standard OpenTelemetry spans to the canonical path with automatic OpenAI tracing and manual agent/retrieval/tool span helpers — see [sdk/python/README.md](sdk/python/README.md), [docs/ADR_003_PYTHON_OTEL_SDK.md](docs/ADR_003_PYTHON_OTEL_SDK.md), and [examples/python_sdk_quickstart](examples/python_sdk_quickstart/)
- **Trace ingestion (v1, legacy):** accept nested span trees from the Python SDK at `POST /v1/traces`
- **Trace and span inspection:** list, filter, and open trace detail with nested span timelines
- **Deterministic trace evidence analysis:** an authenticated `Analyze trace` action on `/app/traces/{id}` runs a fixed rule set (`single-trace-v1`) over stored OTel telemetry via `POST /v2/user/projects/{project}/analysis/traces/{trace_id}` — evidence-backed findings with span navigation, coverage, and explicit limitations; no persistence, no content exposure — see [docs/ANALYST_EVIDENCE_ENGINE.md](docs/ANALYST_EVIDENCE_ENGINE.md)
- **Optional analyst narrative:** when explicitly enabled and requested, a provider may explain existing evidence IDs only (never invent findings); disabled by default and requires dual opt-in flags — see [docs/ADR_005_OPTIONAL_ANALYST_NARRATIVE.md](docs/ADR_005_OPTIONAL_ANALYST_NARRATIVE.md)
- **Project insights (window comparison):** an explicit `Analyze project` action on `/app/insights` compares the selected 24h/7d/30d window against the immediately preceding equal-length window (ruleset `project-window-v1`) via `POST /v2/user/projects/{project}/analysis` — bounded, deterministic cross-trace findings (error-rate/latency/token regressions, outliers, error clusters, instrumentation gaps, error concentration) with real supporting-trace links, coverage, caps metadata, and explicit limitations; synchronous and ephemeral, no persistence or background monitoring — see [docs/PROJECT_INSIGHTS.md](docs/PROJECT_INSIGHTS.md)
- **Self-serve onboarding:** authenticated members of a linked WorkOS organization can create projects and mint/revoke project API keys in the console (`/app/getting-started`, `/app/settings/api-keys`) without the admin CLI — plaintext keys are shown once; only hashes are stored — see [docs/SELF_SERVICE_ONBOARDING.md](docs/SELF_SERVICE_ONBOARDING.md)
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

### Testing

Backend tests run against an isolated PostgreSQL instance (port **5434**, tmpfs storage, distinct from the dev database on 5433) and refuse to start without a dedicated test database URL.

```bash
# Start the isolated test database
docker compose -f docker-compose.test.yml up -d --wait

# Backend tests (from backend/, inside its venv)
cd backend
pip install -r requirements-dev.txt   # once
export HELIOS_TEST_DATABASE_URL=postgresql://helios_test:helios_test@localhost:5434/helios_test
pytest

# Python SDK tests (no database or network needed)
cd sdk/python
pip install -e ".[dev]"               # once
pytest

# Frontend checks
bun run typecheck && bun run lint && bun run build

# Stop and remove the test database
docker compose -f docker-compose.test.yml down -v
```

CI runs the same three suites on every push and pull request (`.github/workflows/ci.yml`).

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

## Canonical v2 authentication

The canonical OTel path (`POST /v1/otlp/traces`, `GET /v2/traces`) is secured
with **project API keys** sent as `Authorization: Bearer <project-api-key>`; the
key determines the project. Keys are managed via the admin CLI:

```bash
cd backend                      # DATABASE_URL set, venv active, migrations applied
python -m app.cli.api_keys create --project-slug demo --name "Local dev" \
  --scopes traces:ingest,traces:read      # prints the key ONCE
python -m app.cli.api_keys list   --project-slug demo
python -m app.cli.api_keys revoke --key-prefix <prefix>
```

Notes:

- Project keys are **secrets**: never commit them or place them in browser code.
- The full key is displayed **only once** at creation and cannot be retrieved later.
- Keys are currently managed through this administrative CLI only.
- **Rate limiting is not implemented yet.**
- Legacy `/v1/traces` remains a temporary **unsecured** compatibility route.

## Human authentication (WorkOS AuthKit)

Humans sign in through **WorkOS AuthKit**; services keep using project API
keys. User JWTs must not be used for OTLP ingestion, and project keys must
never reach browser code. Organization-wide access is the initial model
(per-project membership deferred). Full decision record:
[docs/ADR_004_WORKOS_HUMAN_AUTH.md](docs/ADR_004_WORKOS_HUMAN_AUTH.md).

**WorkOS dashboard setup (manual, once):**

1. Create a WorkOS development environment/application.
2. Configure the redirect URI: `http://localhost:5173/api/auth/callback`.
3. Set the app's sign-in endpoint to `http://localhost:5173/api/auth/sign-in`.
4. Configure the sign-out redirect to `http://localhost:5173/`.
5. Create a WorkOS organization; copy its `org_...` ID.
6. Copy the development `WORKOS_*` credentials into your local `.env`
   (see `.env.example`; server-only — never `VITE_*`, never commit).
7. Link the organization and assign a project (below).

**Local link + verification:**

```bash
# Backend: apply migrations, link the org, assign a project
cd backend && export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
alembic upgrade head
python -m app.cli.organizations create --workos-org-id org_XXX --slug acme --name "Acme"
python -m app.cli.organizations assign-project --workos-org-id org_XXX --project-slug <existing-project>
python -m app.cli.organizations list

# Start backend + frontend, sign in at http://localhost:5173 ("Sign in")
uvicorn app.main:app --reload --port 8000    # terminal 1 (from backend/)
bun dev                                       # terminal 2 (repo root)

# The browser calls these with the WorkOS access token:
#   GET /v2/user/me          -> identity + active organization
#   GET /v2/user/projects    -> projects owned by the linked organization

# Machine paths are unchanged (project API keys):
curl -H "Authorization: Bearer $HELIOS_API_KEY" "http://localhost:8000/v2/traces"
```

Full walkthrough: [docs/ADR_002_PROJECT_API_KEYS.md](docs/ADR_002_PROJECT_API_KEYS.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [examples/otel_quickstart](examples/otel_quickstart/).

## Future improvements

- Browser/user authentication (sessions, OAuth) and rate limiting
- Migrate the frontend and Python SDK onto the authenticated v2 path
- TypeScript SDK and auto-instrumentation
- Eval runner with background workers
- Prompt, dataset, and eval creation workflows (create/run UI actions are placeholders today)
- Production monitoring

See [docs/PROJECT_IMPROVEMENTS.md](docs/PROJECT_IMPROVEMENTS.md) and [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).
