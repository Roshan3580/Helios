# Helios Architecture

Helios is a full-stack observability platform: a React console, FastAPI backend, PostgreSQL storage, and a lightweight Python SDK for trace ingestion.

---

## Component diagram

```mermaid
flowchart TB
    subgraph External["External App"]
        App["RAG Support Bot / LLM App"]
    end

    subgraph SDK["Python SDK"]
        Client["helios_sdk.HeliosClient"]
    end

    subgraph Backend["FastAPI"]
        Ingest["POST /v1/traces"]
        Read["Dashboard & Analytics APIs"]
    end

    subgraph Data["PostgreSQL"]
        DB["Traces · Spans · Projects"]
    end

    subgraph UI["Frontend"]
        Console["React + TanStack Console"]
    end

    App --> Client
    Client --> Ingest
    Ingest --> DB
    Read --> DB
    Console --> Read
```

Source: [diagrams/component.md](../diagrams/component.md)

---

## Frontend architecture

```
src/
├── routes/             # TanStack file routes (/app/*)
├── components/helios/  # Product UI (app shell, project selector, inspectors)
├── contexts/           # ProjectSelectionProvider (authenticated app)
├── lib/api/            # Legacy public client + authenticated /v2/user client
├── lib/otel/           # Duration, status, timeline, JSON helpers
├── hooks/              # use-traces / use-dashboard-summary (v2), legacy analytics hooks
└── styles.css
```

### Routing

| Route                | Purpose                          |
| -------------------- | -------------------------------- |
| `/`                  | Marketing landing page           |
| `/app/dashboard`     | Authenticated OTel overview metrics |
| `/app/traces`        | Authenticated OTel trace list    |
| `/app/traces/:id`    | Authenticated OTel trace detail  |
| `/app/rag-analytics` | RAG quality metrics              |
| `/app/evaluations`   | Eval suites + comparison         |
| `/app/prompts`       | Prompt versions                  |
| `/app/datasets`      | Dataset summaries                |

### Data layer

- **Dashboard (`/app/dashboard`):** WorkOS JWT → `GET /v2/user/projects/.../dashboard`; real `otel_traces` / `otel_spans` aggregates; no demo fallback; no cost estimation.
- **Traces (`/app/traces*`):** WorkOS JWT → `GET /v2/user/projects/.../traces*`; project selector in app shell; no demo fallback.
- **Getting started (`/app/getting-started`):** create projects and mint project API keys under the active linked organization; one-time plaintext reveal; SDK/OTLP setup; explicit telemetry check.
- **API keys (`/app/settings/api-keys`):** list/create/revoke redacted project keys for the selected project.
- **Legacy analytics pages** (RAG, evals, prompts, datasets, experiments, settings): still use `VITE_HELIOS_DEMO_MODE` + unauthenticated `/v1/*` with optional demo fallback.
- Machine ingestion/reads remain project API keys on `/v1/otlp/traces` and `/v2/traces*`.

See [FRONTEND_BACKEND_INTEGRATION.md](FRONTEND_BACKEND_INTEGRATION.md).

---

## Backend architecture

```
backend/app/
├── main.py           # FastAPI app, CORS, router registration
├── models.py         # SQLAlchemy models
├── schemas.py        # Pydantic request/response schemas
├── routers/          # health, projects, traces, dashboard, rag, ...
├── services/         # Business logic and aggregates
├── analyst/          # Deterministic single-trace evidence engine (pure; no LLM)
├── project_analyst/  # Deterministic project-window evidence engine (bounded SQL)
└── seed.py           # Demo seed data
```

See [ANALYST_EVIDENCE_ENGINE.md](ANALYST_EVIDENCE_ENGINE.md) for ruleset
`single-trace-v1` and its authenticated API
(`POST /v2/user/projects/{project_ref}/analysis/traces/{trace_id}`, exposed via
`routers/user_v2.py` → `services/trace_analysis_service.py` → `app/analyst`),
and [PROJECT_INSIGHTS.md](PROJECT_INSIGHTS.md) for ruleset `project-window-v1`
and its project-wide, time-windowed counterpart
(`POST /v2/user/projects/{project_ref}/analysis`, exposed via
`routers/user_v2.py` → `services/project_analysis_service.py` →
`app/project_analyst`, backing the `/app/insights` page). Both are
deterministic, synchronous, bounded, and never persisted; the project engine
compares the selected window against the immediately preceding equal-length
baseline window using project-bound SQL aggregates with capped example
extraction.

Optional narrative explanations are implemented in
`backend/app/analyst_narrative/` behind explicit feature flags (see
[ADR_005_OPTIONAL_ANALYST_NARRATIVE.md](ADR_005_OPTIONAL_ANALYST_NARRATIVE.md))
and are shared by both analysis routes. The provider receives only a
sanitized, bounded evidence bundle (for project analysis: no trace IDs,
project names, or identity) and may not invent findings, alter deterministic
results, or create links.

### API surface (read + write)

| Method | Path                    | Purpose                    | Status |
| ------ | ----------------------- | -------------------------- | ------ |
| POST   | `/v1/otlp/traces`       | OTLP/HTTP protobuf ingest (Bearer key, `traces:ingest`) | **Canonical v2** |
| GET    | `/v2/traces`            | List OTel traces (Bearer key, `traces:read`) | **Canonical v2** |
| GET    | `/v2/traces/{trace_id}` | OTel trace detail (Bearer key, `traces:read`) | **Canonical v2** |
| POST   | `/v1/traces`            | Ingest trace + spans (SDK) | Legacy compatibility |
| GET    | `/v1/traces`            | List traces                | Legacy compatibility |
| GET    | `/v1/traces/{id}`       | Trace detail               | Legacy compatibility |
| GET    | `/v2/user/projects/{ref}/dashboard` | Org-scoped OTel dashboard aggregates (WorkOS JWT) | **Canonical v2** |
| POST   | `/v2/user/projects` | Create project in active linked org (WorkOS JWT) | **Canonical v2** |
| GET    | `/v2/user/projects/{ref}/api-keys` | List redacted project API keys (WorkOS JWT) | **Canonical v2** |
| POST   | `/v2/user/projects/{ref}/api-keys` | Create project API key; plaintext once (WorkOS JWT) | **Canonical v2** |
| POST   | `/v2/user/projects/{ref}/api-keys/{id}/revoke` | Revoke project API key (WorkOS JWT) | **Canonical v2** |
| POST   | `/v2/user/projects/{ref}/analysis` | Deterministic project-window analysis (WorkOS JWT) | **Canonical v2** |
| POST   | `/v2/user/projects/{ref}/analysis/traces/{trace_id}` | Deterministic single-trace analysis (WorkOS JWT) | **Canonical v2** |
| GET    | `/v1/dashboard/summary` | Dashboard aggregates       | Legacy compatibility |
| GET    | `/v1/rag/metrics`       | RAG analytics              | Legacy compatibility |
| GET    | `/v1/evaluations`       | Eval runs                  | Legacy compatibility |
| GET    | `/v1/prompts`           | Prompt versions            | Legacy compatibility |
| GET    | `/v1/datasets`          | Dataset summaries          | Legacy compatibility |
| POST   | `/v1/demo/seed`         | Seed sample data           | Legacy compatibility |

### Canonical v2: OpenTelemetry path

Decision records: [ADR_001_OTLP_TRACE_FOUNDATION.md](ADR_001_OTLP_TRACE_FOUNDATION.md)
(protocol/schema/storage) and [ADR_002_PROJECT_API_KEYS.md](ADR_002_PROJECT_API_KEYS.md)
(authentication).

- **Authentication (machines):** canonical routes require
  `Authorization: Bearer <project-api-key>`. The key determines the project;
  there is no project slug header or query parameter. Ingestion needs scope
  `traces:ingest`; reads need `traces:read`. Missing/invalid credentials → 401
  (`WWW-Authenticate: Bearer`); valid key without the scope → 403. Project keys
  are **secrets** — never commit them or put them in browser code. Keys are
  managed by the admin CLI `python -m app.cli.api_keys` or the self-serve
  human routes under `/v2/user/projects/{ref}/api-keys` (see
  [SELF_SERVICE_ONBOARDING.md](SELF_SERVICE_ONBOARDING.md)).
- **Authentication (humans):** WorkOS AuthKit signs users in
  ([ADR_004_WORKOS_HUMAN_AUTH.md](ADR_004_WORKOS_HUMAN_AUTH.md)). The browser
  calls `GET /v2/user/me`, `GET /v2/user/projects`,
  `GET /v2/user/projects/{project}/dashboard`, and
  `GET /v2/user/projects/{project}/traces[/{trace_id}]` with
  `Authorization: Bearer <WorkOS access token>`; FastAPI verifies the JWT
  against the WorkOS JWKS and scopes access to the organization in the token's
  `org_id`. Organizations are linked and projects assigned via
  `python -m app.cli.organizations`. **User JWTs must not be used for OTLP
  ingestion, and project keys must never be used by browsers.**
  Organization-wide access is the initial model; per-project user membership
  is deferred.
- `POST /v1/otlp/traces` accepts official OTLP/HTTP **protobuf**
  (`Content-Type: application/x-protobuf`); `X-Helios-Environment` is an
  optional environment fallback. Spans persist into `otel_traces`/`otel_spans`
  (migrations `002_otel_foundation`, `003_project_api_keys`) incrementally and
  idempotently; trace summaries are recomputed from stored spans.
- `GET /v2/traces` and `GET /v2/traces/{trace_id}` return only the
  authenticated project's traces; another project's trace is a 404.
- Reference client: [examples/otel_quickstart](../examples/otel_quickstart/)
  (official OTel SDK + OTLP/HTTP exporter, `HELIOS_API_KEY`).
- Not yet: browser/user authentication, rate limiting, OTLP/gRPC, collector
  support, auto-instrumentation, frontend on v2 data. This is not
  production-ready.

#### Local verification (v2 path)

```bash
# 1. Isolated test DB + backend tests (applies migrations automatically)
docker compose -f docker-compose.test.yml up -d --wait
cd backend
export HELIOS_TEST_DATABASE_URL=postgresql://helios_test:helios_test@localhost:5434/helios_test
pytest

# 2. Local dev backend (applies migrations 001-003 to the dev database)
docker compose -f docker-compose.dev.yml up -d postgres
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 3. Create a project key (prints the key once) and export it
python -m app.cli.api_keys create --project-slug otel-quickstart \
  --project-name "OTel Quickstart" --environment development \
  --name "Local dev" --scopes traces:ingest,traces:read
export HELIOS_API_KEY=<the key printed once>

# 4. OTel quickstart (see examples/otel_quickstart/README.md for setup)
python examples/otel_quickstart/main.py --api-url http://localhost:8000

# 5. Canonical v2 reads (project derived from the key)
curl -H "Authorization: Bearer $HELIOS_API_KEY" "http://localhost:8000/v2/traces"
curl -H "Authorization: Bearer $HELIOS_API_KEY" "http://localhost:8000/v2/traces/<trace_id>"

# 6. Scoped keys: ingest-only cannot read (403), read-only cannot ingest (403)
python -m app.cli.api_keys create --project-slug otel-quickstart --name ingest \
  --scopes traces:ingest
python -m app.cli.api_keys create --project-slug otel-quickstart --name read \
  --scopes traces:read

# 7. Revoke a key -> future use returns 401
python -m app.cli.api_keys list --project-slug otel-quickstart
python -m app.cli.api_keys revoke --key-prefix <prefix>

# 8. Legacy v1 demo still works unchanged (no auth)
python examples/rag_support_bot/run_demo.py --api-url http://localhost:8000
```

---

## Request flow (UI read path)

```mermaid
sequenceDiagram
    participant Browser as React Console
    participant API as FastAPI
    participant DB as PostgreSQL

    Browser->>API: GET /v1/traces
    API->>DB: SELECT traces + project
    DB-->>API: rows
    API-->>Browser: JSON trace list

    Browser->>API: GET /v1/traces/{trace_id}
    API->>DB: SELECT trace + spans
    DB-->>API: span tree
    API-->>Browser: trace detail JSON
```

---

## Ingestion flow (SDK write path)

```mermaid
flowchart TB
    Query["User Query"]
    Retriever["Retriever"]
    Reranker["Reranker"]
    LLM["LLM"]
    Tool["Tool"]
    Response["Response"]
    SDK["Python SDK"]
    API["POST /v1/traces"]
    Database["PostgreSQL"]
    Frontend["Frontend /app/traces"]

    Query --> Retriever --> Reranker --> LLM --> Tool --> Response
    Response --> SDK --> API --> Database --> Frontend
```

Source: [diagrams/trace-lifecycle.md](../diagrams/trace-lifecycle.md)

```mermaid
sequenceDiagram
    participant App as External App
    participant SDK as helios_sdk
    participant API as FastAPI
    participant DB as PostgreSQL

    App->>SDK: build trace + spans
    SDK->>API: POST /v1/traces
    API->>DB: INSERT project, trace, spans
    DB-->>API: committed
    API-->>SDK: 201 trace detail
```

See [SDK_INGESTION.md](SDK_INGESTION.md) for install and demo steps.

---

## Local deployment

```mermaid
flowchart LR
    subgraph Dev["Developer Machine"]
        FE["Frontend<br/>Vite :5173"]
        BE["Backend<br/>FastAPI :8000"]
        Demo["RAG Demo App"]
    end

    subgraph Infra["Docker"]
        PG["PostgreSQL<br/>:5433"]
    end

    Demo --> BE
    FE --> BE
    BE --> PG
```

Source: [diagrams/deployment.md](../diagrams/deployment.md)

---

## Tracing model

OpenTelemetry-inspired hierarchy stored in Postgres:

```
Trace
├── Span (user.query)          input
│   ├── Span (retriever.*)     rag
│   ├── Span (llm.*)           llm
│   ├── Span (tool.*)          tool
│   └── Span (response.*)      output
```

Each span stores: `span_id`, `parent_span_id`, `name`, `span_type`, timing, tokens, cost, status, previews, `metadata_json`.

---

## Design tradeoffs

| Decision                             | Why                                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------- |
| **FastAPI**                          | Typed Pydantic schemas, auto OpenAPI docs, fast local dev for portfolio backend |
| **PostgreSQL**                       | Relational trace/span trees, Alembic migrations, familiar ops story             |
| **SDK instead of UI-only ingestion** | Proves external apps can emit observability data: core recruiting signal        |
| **Demo fallback in frontend**        | UI stays usable without backend; live mode proves integration                   |
| **Read APIs + seed data**            | Dashboard/RAG/evals work before workers exist                                   |
| **No auth (yet)**                    | Keeps scope focused on ingestion + visualization                                |

### Why not OpenTelemetry yet?

OTel compatibility is planned. The current SDK is intentionally minimal to demonstrate `POST /v1/traces` end-to-end without exporter complexity.

### Why not direct UI ingestion?

Production LLM apps run outside the browser. The SDK + RAG demo shows Helios as a platform boundary, not just a static dashboard.

---

## Future architecture (not implemented)

- Redis + Celery/RQ for eval workers
- API key auth and rate limiting
- OpenTelemetry exporter → ingestion adapter
- TypeScript SDK for Node/browser apps

See [BACKEND_PLAN.md](BACKEND_PLAN.md).
