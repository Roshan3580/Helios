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
├── routes/           # TanStack file routes (/app/*)
├── components/helios/  # Product UI (app shell, primitives, demo data)
├── lib/api/          # Backend client, types, mappers
├── hooks/            # use-traces, use-dashboard-summary, etc.
└── styles.css
```

### Routing

| Route                | Purpose                          |
| -------------------- | -------------------------------- |
| `/`                  | Marketing landing page           |
| `/app/dashboard`     | Overview metrics + recent traces |
| `/app/traces`        | Trace list                       |
| `/app/traces/:id`    | Trace detail + span timeline     |
| `/app/rag-analytics` | RAG quality metrics              |
| `/app/evaluations`   | Eval suites + comparison         |
| `/app/prompts`       | Prompt versions                  |
| `/app/datasets`      | Dataset summaries                |

### Data layer

- `VITE_HELIOS_DEMO_MODE=true` → static demo data
- `VITE_HELIOS_DEMO_MODE=false` → fetch from `VITE_API_BASE_URL`
- On API failure → demo fallback + subtle banner

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
└── seed.py           # Demo seed data
```

### API surface (read + write)

| Method | Path                    | Purpose                    |
| ------ | ----------------------- | -------------------------- |
| POST   | `/v1/traces`            | Ingest trace + spans (SDK) |
| GET    | `/v1/traces`            | List traces                |
| GET    | `/v1/traces/{id}`       | Trace detail               |
| GET    | `/v1/dashboard/summary` | Dashboard aggregates       |
| GET    | `/v1/rag/metrics`       | RAG analytics              |
| GET    | `/v1/evaluations`       | Eval runs                  |
| GET    | `/v1/prompts`           | Prompt versions            |
| GET    | `/v1/datasets`          | Dataset summaries          |
| POST   | `/v1/demo/seed`         | Seed sample data           |

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
| **SDK instead of UI-only ingestion** | Proves external apps can emit observability data — core recruiting signal       |
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
