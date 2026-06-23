# Helios Backend Implementation Plan

## Recommended stack

| Layer          | Technology                     |
| -------------- | ------------------------------ |
| API framework  | FastAPI                        |
| Database       | PostgreSQL 16+                 |
| Cache / queues | Redis                          |
| Task workers   | Celery or RQ                   |
| ORM            | SQLAlchemy 2.x                 |
| Migrations     | Alembic                        |
| Trace model    | OpenTelemetry-compatible spans |
| Auth (later)   | JWT or API keys per project    |

## Backend modules

```
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── api/
│   │   ├── v1/
│   │   │   ├── traces.py
│   │   │   ├── spans.py
│   │   │   ├── prompts.py
│   │   │   ├── evals.py
│   │   │   ├── datasets.py
│   │   │   ├── rag_analytics.py
│   │   │   ├── experiments.py
│   │   │   └── projects.py
│   │   └── ingestion/
│   │       └── sdk.py
│   ├── models/
│   ├── schemas/
│   ├── services/
│   └── workers/
├── alembic/
└── tests/
```

## API endpoints to build

### Ingestion

| Method | Path         | Description                     |
| ------ | ------------ | ------------------------------- |
| POST   | `/v1/traces` | Ingest trace with spans (batch) |
| POST   | `/v1/spans`  | Append spans to existing trace  |

### Traces

| Method | Path                    | Description                    |
| ------ | ----------------------- | ------------------------------ |
| GET    | `/v1/traces`            | List traces (filter, paginate) |
| GET    | `/v1/traces/{trace_id}` | Get trace with span tree       |
| DELETE | `/v1/traces/{trace_id}` | Delete trace                   |

### Prompts

| Method | Path                        | Description        |
| ------ | --------------------------- | ------------------ |
| GET    | `/v1/prompts`               | List prompts       |
| POST   | `/v1/prompts`               | Create prompt      |
| GET    | `/v1/prompts/{id}/versions` | List versions      |
| POST   | `/v1/prompts/{id}/versions` | Create new version |

### Evaluations

| Method | Path                      | Description      |
| ------ | ------------------------- | ---------------- |
| GET    | `/v1/evals`               | List eval suites |
| POST   | `/v1/evals/runs`          | Start eval run   |
| GET    | `/v1/evals/runs/{run_id}` | Get run results  |

### Datasets

| Method | Path                      | Description    |
| ------ | ------------------------- | -------------- |
| GET    | `/v1/datasets`            | List datasets  |
| POST   | `/v1/datasets`            | Create dataset |
| POST   | `/v1/datasets/{id}/items` | Add items      |

### RAG Analytics

| Method | Path              | Description            |
| ------ | ----------------- | ---------------------- |
| GET    | `/v1/rag/metrics` | Aggregated RAG metrics |
| GET    | `/v1/rag/traces`  | Traces with RAG spans  |

### Projects

| Method | Path           | Description    |
| ------ | -------------- | -------------- |
| GET    | `/v1/projects` | List projects  |
| POST   | `/v1/projects` | Create project |

## Data model plan

### Core tables

```sql
projects (id, name, slug, created_at)
traces (id, project_id, name, status, started_at, duration_ms, metadata JSONB)
spans (id, trace_id, parent_span_id, name, kind, started_at, ended_at, status, attributes JSONB)
prompts (id, project_id, name, created_at)
prompt_versions (id, prompt_id, version, content, model, metadata JSONB, created_at)
datasets (id, project_id, name, created_at)
dataset_items (id, dataset_id, input JSONB, expected_output JSONB)
eval_suites (id, project_id, name, dataset_id, prompt_version_id, config JSONB)
eval_runs (id, suite_id, status, started_at, completed_at, results JSONB)
experiments (id, project_id, name, config JSONB, created_at)
```

### Indexing strategy

- `traces(project_id, started_at DESC)` — list view
- `traces(project_id, status)` — error filtering
- `spans(trace_id, parent_span_id)` — tree reconstruction
- GIN index on `spans.attributes` for model/provider filters

## Implementation phases

### Phase 1 — Foundation

- [x] FastAPI project scaffold (`backend/app/`)
- [x] PostgreSQL schema + Alembic migrations
- [x] Trace/span ingestion endpoint (`POST /v1/traces`)
- [x] Trace list + detail query endpoints
- [x] Project list endpoint (`GET /v1/projects`)
- [x] Health endpoint with DB connectivity check
- [x] Demo seed endpoint (`POST /v1/demo/seed`)
- [x] Docker Compose for local Postgres + backend
- [x] Connect frontend trace pages to API
- [x] Prompt/eval/RAG read APIs for app pages

### Phase 2 — Frontend integration and read APIs

- [x] Frontend API client (`src/lib/api/`)
- [x] Wire `/app/traces` to `GET /v1/traces`
- [x] Wire `/app/traces/:id` to `GET /v1/traces/{trace_id}`
- [x] Demo fallback when backend unavailable
- [x] Status mapper (`warning` → `warn`)
- [x] Wire dashboard overview to backend metrics
- [x] Prompt/eval/RAG read APIs for remaining app pages
- [x] Wire dashboard, RAG, evals, prompts, and datasets pages

### Phase 3 — Prompts and evals (4–6 weeks)

- Prompt CRUD and versioning
- Dataset management
- Eval run worker (Celery/RQ)
- Eval results API
- Connect frontend eval pages

### Phase 4 — SDK ingestion (current)

- [x] Lightweight Python SDK (`sdk/python/helios_sdk`)
- [x] External RAG support bot demo (`examples/rag_support_bot`)
- [x] Trace submission via existing `POST /v1/traces`
- [ ] OpenTelemetry-compatible exporter
- [ ] TypeScript SDK
- [ ] API key auth per project

### Phase 5 — Prompts, evals, and workers (4–6 weeks)

- Deployment (Docker, CI/CD)
- Monitoring and alerting
- Documentation and onboarding guides
