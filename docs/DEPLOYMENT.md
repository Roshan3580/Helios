# Helios Deployment Guide

Step-by-step instructions for deploying Helios as a public portfolio demo. This guide covers configuration only — run deployments in Phase B/C after reviewing env vars here.

## Recommended stack

| Layer        | Platform                                      | Notes                                                 |
| ------------ | --------------------------------------------- | ----------------------------------------------------- |
| **Frontend** | [Vercel](https://vercel.com)                  | TanStack Start + Nitro SSR; use Bun for install/build |
| **Backend**  | [Railway](https://railway.app)                | Docker or Python service; override `$PORT` supported  |
| **Database** | Railway Postgres or [Neon](https://neon.tech) | Standard PostgreSQL 16; no Redis/workers required     |

**Alternative:** Render (web service + Postgres) for backend/DB; Lovable publish for frontend if you prefer zero Vercel config.

---

## Architecture overview

See [diagrams/production-deployment.md](../diagrams/production-deployment.md) for the production topology.

```
Vercel (React console)  →  Railway (FastAPI)  →  Postgres
External RAG demo app   →  Python SDK         →  POST /v1/traces
```

---

## Environment variable matrix

### Backend (Railway service)

| Variable           | Required | Example / notes                                                                                        |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`     | Yes      | `postgresql://user:pass@host:5432/helios?sslmode=require` (Neon/Supabase often need `sslmode=require`) |
| `CORS_ORIGINS`     | Yes      | Comma-separated frontend origins, e.g. `https://helios.example.com,https://helios.example.com/`        |
| `HELIOS_DEMO_MODE` | Yes      | `true` to enable `POST /v1/demo/seed`; set `false` after initial seeding                               |
| `BACKEND_HOST`     | No       | Default `0.0.0.0` — uvicorn bind address                                                               |
| `BACKEND_PORT`     | No       | Default `8000`; Railway injects `$PORT` (Dockerfile uses it)                                           |

### Frontend (Vercel project)

| Variable                | Required | Example / notes                                           |
| ----------------------- | -------- | --------------------------------------------------------- |
| `VITE_API_BASE_URL`     | Yes      | `https://<backend-url>` — **no trailing slash**           |
| `VITE_HELIOS_DEMO_MODE` | Yes      | `false` for live demo; `true` for static in-app demo only |

> **Build-time warning:** `VITE_*` variables are embedded at **build time** on Vercel. Changing them requires a redeploy. Set them in **Project → Settings → Environment Variables** before the first production build.

### Demo mode semantics

| `VITE_HELIOS_DEMO_MODE` | Backend | Frontend behavior                                            |
| ----------------------- | ------- | ------------------------------------------------------------ |
| `true`                  | any     | Static demo data; no API calls                               |
| `false`                 | up      | Live API data                                                |
| `false`                 | down    | Demo fallback + “Demo fallback · backend unavailable” banner |

---

## Railway backend setup

### 1. Create project and database

1. Create a Railway project.
2. Add **PostgreSQL** (Railway plugin) or create a Neon database and copy its connection string.
3. If using Neon/Supabase, append `?sslmode=require` to `DATABASE_URL` if connections fail without SSL.

### 2. Deploy backend service

**Option A — Dockerfile (recommended)**

1. Add a service from this repo; set **Root Directory** to `backend`.
2. Railway builds `backend/Dockerfile`, which runs migrations then starts uvicorn:

   ```bash
   alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
   ```

3. Set environment variables (see matrix above).
4. Generate a public domain (e.g. `https://<backend-url>`).

**Option B — Nixpacks / Python**

If not using Docker, set the start command:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Install from `backend/requirements.txt`; working directory must be `backend/`.

### 3. Verify backend

```bash
curl https://<backend-url>/health
```

Expected: `"status": "ok"`, `"database": "connected"`.

### 4. Seed demo data (once)

Requires `HELIOS_DEMO_MODE=true` on the backend:

```bash
curl -X POST https://<backend-url>/v1/demo/seed
```

Expected JSON with `traces_seeded`, `prompt_versions_seeded`, etc.

Re-running seed is partially idempotent (existing trace IDs are skipped; prompts/evals/RAG metrics are refreshed for the `acme` project).

### 5. Disable public seed (recommended after seeding)

Set on Railway:

```
HELIOS_DEMO_MODE=false
```

`POST /v1/demo/seed` then returns **403**. Trace ingestion (`POST /v1/traces`) remains open — see [Portfolio scope](#portfolio-scope-intentional-limitations) below.

---

## Vercel frontend setup

### 1. Import repository

1. Connect the GitHub repo to Vercel.
2. **Framework preset:** Vercel should detect TanStack Start (Nitro is bundled via `@lovable.dev/vite-tanstack-config`).

### 2. Build settings

| Setting          | Value              |
| ---------------- | ------------------ |
| Install Command  | `bun install`      |
| Build Command    | `bun run build`    |
| Output Directory | (auto — Nitro/SSR) |

Use **Node.js 20+** in Project Settings → General.

### 3. Environment variables (Production)

Set before building:

```
VITE_API_BASE_URL=https://<backend-url>
VITE_HELIOS_DEMO_MODE=false
```

Redeploy after any change to `VITE_*` vars.

### 4. Verify frontend

1. Open `https://<frontend-url>/app/dashboard` — metrics should match seeded backend data.
2. Open `/app/traces` — list should include seeded `trc_...` rows.
3. No “Demo fallback · backend unavailable” banner when backend is healthy.

---

## Post-deploy checklist

- [ ] `GET <backend-url>/health` → database connected
- [ ] `POST <backend-url>/v1/demo/seed` → success (with `HELIOS_DEMO_MODE=true`)
- [ ] `CORS_ORIGINS` includes exact Vercel URL (scheme + host, no path)
- [ ] Vercel build used `VITE_HELIOS_DEMO_MODE=false` and correct `VITE_API_BASE_URL`
- [ ] Dashboard and traces show live data
- [ ] Set `HELIOS_DEMO_MODE=false` on backend after seeding
- [ ] Update README with real `<frontend-url>` and `<backend-url>` (Phase E)

---

## SDK demo against production API

From your machine (repo root):

```bash
python -m venv .venv-demo && source .venv-demo/bin/activate
pip install -r examples/rag_support_bot/requirements.txt
python examples/rag_support_bot/run_demo.py \
  --api-url https://<backend-url> \
  --query "How do I rotate API keys without downtime?"
```

The script prints a new `trace_id` and a link to `/app/traces/<trace_id>` on your deployed frontend (update the printed localhost link manually or pass a frontend base URL if the script supports it).

---

## CORS troubleshooting

**Symptom:** Browser console shows CORS errors; frontend shows fallback banner.

**Fixes:**

1. Set `CORS_ORIGINS` to the exact frontend origin:
   - `https://your-app.vercel.app` (no trailing path)
   - Include both `www` and apex if you use both
   - For preview deploys, add `https://your-app-*.vercel.app` or each preview URL
2. Redeploy/restart backend after changing `CORS_ORIGINS`.
3. Confirm `VITE_API_BASE_URL` uses `https://` and matches the Railway public URL.
4. Check Railway logs for uvicorn startup and migration errors.

**Test CORS from terminal:**

```bash
curl -i -H "Origin: https://<frontend-url>" https://<backend-url>/health
```

Look for `access-control-allow-origin` in the response headers.

---

## SSL / Postgres notes

- **Railway Postgres:** SSL is often handled in the provided connection string; follow Railway docs.
- **Neon / Supabase:** Use the pooled or direct connection string from the dashboard. If you see SSL errors, append:

  ```
  ?sslmode=require
  ```

- **Local dev:** `docker-compose.dev.yml` uses non-SSL Postgres on port **5433** — unchanged by production setup.

---

## Local Docker Compose (unchanged)

`docker-compose.dev.yml` overrides the container start command and still runs:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Port **8000** is fixed in compose; `$PORT` is for Railway/Render-style hosts.

---

## Portfolio scope (intentional limitations)

Helios is a **portfolio MVP**, not production SaaS. After deployment, these remain true:

- **No auth** — `POST /v1/traces` is open; anyone can ingest traces
- **No rate limiting** — public URL can receive abuse/spam traces
- **Demo seed** — when `HELIOS_DEMO_MODE=true`, anyone can call `/v1/demo/seed`
- **Sample-scale metrics** — dashboard/RAG numbers are illustrative
- **Demo-only UI** — create/run buttons show a placeholder notice
- **`/app/experiments`** — static demo data only (not wired to API)
- **No workers, OTel, or billing**

Disable demo seed after initial setup; plan auth/rate limiting before any non-portfolio use.

---

## Related docs

- [FRONTEND_BACKEND_INTEGRATION.md](FRONTEND_BACKEND_INTEGRATION.md) — demo mode and API wiring
- [SDK_INGESTION.md](SDK_INGESTION.md) — Python SDK and RAG demo
- [diagrams/production-deployment.md](../diagrams/production-deployment.md) — Mermaid topology
- [diagrams/deployment.md](../diagrams/deployment.md) — local dev topology
