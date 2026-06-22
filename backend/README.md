# Helios Backend

FastAPI backend for trace ingestion, project scoping, and demo seed data.

## Requirements

- Python 3.12+
- PostgreSQL 16+

## Local setup (without Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=postgresql://helios:helios@localhost:5432/helios
export HELIOS_DEMO_MODE=true

alembic upgrade head
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Docker Compose (recommended)

From the repository root:

```bash
docker compose -f docker-compose.dev.yml up --build
```

## Seed demo data

```bash
curl -X POST http://localhost:8000/v1/demo/seed
```

## API overview

| Method | Path | Description |
| ------ | ---- | ----------- |
| GET | `/health` | Health and database status |
| GET | `/v1/projects` | List projects |
| GET | `/v1/traces` | List traces |
| GET | `/v1/traces/{trace_id}` | Trace detail with spans |
| POST | `/v1/traces` | Ingest trace + spans |
| POST | `/v1/demo/seed` | Seed sample observability data |

Interactive docs: http://localhost:8000/docs
