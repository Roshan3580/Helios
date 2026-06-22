# Frontend ↔ Backend Integration

## Environment

| Variable                | Default                 | Description                        |
| ----------------------- | ----------------------- | ---------------------------------- |
| `VITE_API_BASE_URL`     | `http://localhost:8000` | Helios FastAPI base URL            |
| `VITE_HELIOS_DEMO_MODE` | `true`                  | When `true`, uses static demo data |

Set `VITE_HELIOS_DEMO_MODE=false` to load traces from the backend. If the API is unreachable, the traces pages fall back to local demo data and show a **Demo fallback** notice.

## Wired pages (Phase 2)

| Route             | API endpoint                |
| ----------------- | --------------------------- |
| `/app/traces`     | `GET /v1/traces`            |
| `/app/traces/:id` | `GET /v1/traces/{trace_id}` |

## Status mapping

| Backend   | Frontend  |
| --------- | --------- |
| `success` | `success` |
| `warning` | `warn`    |
| `error`   | `error`   |

## Local verification

```bash
# Terminal 1 — backend
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
alembic upgrade head && uvicorn app.main:app --reload --port 8000
curl -X POST http://localhost:8000/v1/demo/seed

# Terminal 2 — frontend with live API
cp .env.example .env
# Set VITE_HELIOS_DEMO_MODE=false
bun dev
```

Open `/app/traces` — traces should load from the API.
