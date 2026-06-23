# Frontend ↔ Backend Integration

## Environment

| Variable                | Default                 | Description                        |
| ----------------------- | ----------------------- | ---------------------------------- |
| `VITE_API_BASE_URL`     | `http://localhost:8000` | Helios FastAPI base URL            |
| `VITE_HELIOS_DEMO_MODE` | `true`                  | When `true`, uses static demo data |

Set `VITE_HELIOS_DEMO_MODE=false` to load data from the backend. If the API is unreachable, pages fall back to local demo data and show a **Demo fallback · backend unavailable** notice.

## Wired pages

### Phase 2 — Traces

| Route             | API endpoint                |
| ----------------- | --------------------------- |
| `/app/traces`     | `GET /v1/traces`            |
| `/app/traces/:id` | `GET /v1/traces/{trace_id}` |

### Phase 3 — Dashboard & analytics

| Route                | API endpoint                |
| -------------------- | --------------------------- |
| `/app/dashboard`     | `GET /v1/dashboard/summary` |
|                      | `GET /v1/prompts` (failing) |
| `/app/rag-analytics` | `GET /v1/rag/metrics`       |
| `/app/evaluations`   | `GET /v1/evaluations`       |
| `/app/prompts`       | `GET /v1/prompts`           |
| `/app/datasets`      | `GET /v1/datasets`          |

All Phase 3 list endpoints accept optional `?project_slug=acme`.

## Status mapping

| Backend   | Frontend  |
| --------- | --------- |
| `success` | `success` |
| `warning` | `warn`    |
| `error`   | `error`   |

RAG chunk status: `ok` → success badge, `drift` → warn, `low` → danger.

## Demo fallback behavior

| `VITE_HELIOS_DEMO_MODE` | Backend available | Result                      |
| ----------------------- | ----------------- | --------------------------- |
| `true`                  | any               | Static demo data, no banner |
| `false`                 | yes               | Live API data, no banner    |
| `false`                 | no                | Demo fallback + banner      |

## Local verification

```bash
# Terminal 1 — backend
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
export HELIOS_DEMO_MODE=true
alembic upgrade head && uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/v1/demo/seed

# Smoke test Phase 3 endpoints
curl http://localhost:8000/v1/dashboard/summary?project_slug=acme
curl http://localhost:8000/v1/rag/metrics?project_slug=acme
curl http://localhost:8000/v1/evaluations?project_slug=acme
curl http://localhost:8000/v1/prompts?project_slug=acme
curl http://localhost:8000/v1/datasets?project_slug=acme

# Terminal 2 — frontend with live API
cp .env.example .env
# Set VITE_HELIOS_DEMO_MODE=false
bun dev
```

Open `/app/dashboard`, `/app/rag-analytics`, `/app/evaluations`, `/app/prompts`, and `/app/datasets` — values should load from the API when demo mode is off.
