# Helios Deployment Guide

Step-by-step instructions for deploying Helios as a public portfolio demo. This guide covers configuration only; run deployments manually from the Render/Vercel dashboards (not from Cursor).

## Recommended stack (free tier)

| Layer        | Platform                                                                        | Notes                                                 |
| ------------ | ------------------------------------------------------------------------------- | ----------------------------------------------------- |
| **Frontend** | [Vercel](https://vercel.com)                                                    | TanStack Start + Nitro SSR; use Bun for install/build |
| **Backend**  | [Render](https://render.com) Web Service                                        | Python or Docker; `$PORT` injected at runtime         |
| **Database** | Render Postgres (primary) or [Supabase](https://supabase.com) Postgres (backup) | Standard PostgreSQL 16; no Redis/workers required     |

> **Free-tier note:** Render free web services **sleep after ~15 minutes of inactivity**. The first request after sleep triggers a **cold start** (often 30-60+ seconds). Health checks, seed curls, and the frontend may appear slow until the service wakes. This is fine for a portfolio demo; upgrade to a paid Render instance for always-on.

**Alternatives:** [Railway](#alternative-railway) (if you have an active plan); Lovable publish for frontend if you prefer zero Vercel config.

---

## Architecture overview

See [diagrams/production-deployment.md](../diagrams/production-deployment.md) for the production topology.

```
Vercel (React console)  →  Render (FastAPI)  →  Render Postgres
External RAG demo app   →  Python SDK       →  POST /v1/traces
```

---

## Environment variable matrix

### Backend (Render Web Service)

| Variable           | Required | Example / notes                                                                                   |
| ------------------ | -------- | ------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`     | Yes      | From Render Postgres **Internal Database URL**, or Supabase URI with `?sslmode=require` if needed |
| `CORS_ORIGINS`     | Yes      | Comma-separated origins, e.g. `http://localhost:5173,https://<frontend-url>`                      |
| `HELIOS_DEMO_MODE` | Yes      | `true` to enable `POST /v1/demo/seed`; set `false` after initial seeding                          |
| `BACKEND_HOST`     | No       | Default `0.0.0.0`: uvicorn bind address                                                           |
| `BACKEND_PORT`     | No       | Default `8000` locally; Render injects `$PORT` at runtime                                         |

### Frontend (Vercel project)

| Variable                | Required | Example / notes                                           |
| ----------------------- | -------- | --------------------------------------------------------- |
| `VITE_API_BASE_URL`     | Yes      | `https://<render-backend-url>`: **no trailing slash**     |
| `VITE_HELIOS_DEMO_MODE` | Yes      | `false` for live demo; `true` for static in-app demo only |

> **Build-time warning:** `VITE_*` variables are embedded at **build time** on Vercel. Changing them requires a redeploy. Set them in **Project → Settings → Environment Variables** before the first production build.

### Demo mode semantics

| `VITE_HELIOS_DEMO_MODE` | Backend | Frontend behavior                                            |
| ----------------------- | ------- | ------------------------------------------------------------ |
| `true`                  | any     | Static demo data; no API calls                               |
| `false`                 | up      | Live API data                                                |
| `false`                 | down    | Demo fallback + “Demo fallback · backend unavailable” banner |

---

## Render Postgres setup

### Option A: Render Postgres (recommended)

1. [Render Dashboard](https://dashboard.render.com) → **New +** → **PostgreSQL**.
2. Name it (e.g. `helios-db`); choose **Free** tier if available in your region.
3. After creation, open the database → **Connections**:
   - Copy **Internal Database URL** for the backend web service on Render (preferred: lower latency, no egress).
   - **External Database URL** is for tools outside Render (local `psql`, one-off scripts).

### Option B: Supabase Postgres (backup)

Use if Render Postgres is unavailable or you already use Supabase:

1. Create a Supabase project → **Project Settings → Database**.
2. Copy the **URI** connection string (Session or Transaction pooler).
3. Append `?sslmode=require` if connections fail without SSL.
4. Set as `DATABASE_URL` on the Render backend service.

---

## Render backend setup

### 1. Create Web Service

1. **New +** → **Web Service** → connect GitHub repo **`Roshan3580/Helios`** (or your fork).
2. Configure:

| Setting            | Value                                                      |
| ------------------ | ---------------------------------------------------------- |
| **Name**           | `helios-backend` (example)                                 |
| **Region**         | Same as Postgres when possible                             |
| **Root Directory** | `backend`                                                  |
| **Runtime**        | **Docker** (uses `backend/Dockerfile`) **or** **Python 3** |

**If using Python 3 (no Docker):**

| Setting           | Value                                                                      |
| ----------------- | -------------------------------------------------------------------------- |
| **Build Command** | `pip install -r requirements.txt`                                          |
| **Start Command** | `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |

**If using Docker:** Render builds `backend/Dockerfile`, which runs:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
```

You can still set an explicit **Start Command** on Render if needed; use the Python form with `$PORT`.

3. **Health Check Path:** `/health`
4. **Instance type:** Free (for portfolio demo)

### 2. Environment variables

In the web service → **Environment**:

| Key                | Value                                                              |
| ------------------ | ------------------------------------------------------------------ |
| `DATABASE_URL`     | Paste Internal Database URL from Render Postgres (or Supabase URI) |
| `CORS_ORIGINS`     | `http://localhost:5173` initially; add Vercel URL after Phase C    |
| `HELIOS_DEMO_MODE` | `true`                                                             |

### 3. Deploy and get public URL

1. Click **Create Web Service** (or **Manual Deploy**).
2. Wait for build + deploy logs; confirm Alembic migration and uvicorn startup.
3. Copy the public URL, e.g. `https://helios-backend.onrender.com` → this is `<render-backend-url>`.

### 4. Verify backend

Allow for cold start on free tier (retry after 30-60s if the first request times out):

```bash
curl https://<render-backend-url>/health
```

Expected:

```json
{ "status": "ok", "version": "0.1.0", "database": "connected", "demo_mode": true }
```

### 5. Seed demo data (once)

Requires `HELIOS_DEMO_MODE=true`:

```bash
curl -X POST https://<render-backend-url>/v1/demo/seed
```

Expected JSON with `traces_seeded`, `prompt_versions_seeded`, etc.

Verify data:

```bash
curl https://<render-backend-url>/v1/projects
curl https://<render-backend-url>/v1/traces
curl "https://<render-backend-url>/v1/dashboard/summary?project_slug=acme"
```

Re-running seed is partially idempotent (existing trace IDs are skipped; prompts/evals/RAG metrics are refreshed for the `acme` project).

### 6. Disable public seed (recommended after seeding)

On Render → Environment:

```
HELIOS_DEMO_MODE=false
```

`POST /v1/demo/seed` then returns **403**. Trace ingestion (`POST /v1/traces`) remains open; see [Portfolio scope](#portfolio-scope-intentional-limitations).

---

## Vercel frontend setup

### 1. Import repository

1. Connect the GitHub repo to Vercel.
2. **Framework preset:** Vercel should detect TanStack Start (Nitro is bundled via `@lovable.dev/vite-tanstack-config`).

### 2. Build settings

| Setting          | Value             |
| ---------------- | ----------------- |
| Install Command  | `bun install`     |
| Build Command    | `bun run build`   |
| Output Directory | (auto: Nitro/SSR) |

Use **Node.js 20+** in Project Settings → General.

### 3. Environment variables (Production)

Set before building:

```
VITE_API_BASE_URL=https://<render-backend-url>
VITE_HELIOS_DEMO_MODE=false
```

Redeploy after any change to `VITE_*` vars.

### 4. Update Render CORS (after frontend deploy)

Add your Vercel URL to Render backend env:

```
CORS_ORIGINS=http://localhost:5173,https://<frontend-url>
```

Redeploy or restart the Render service after changing `CORS_ORIGINS`.

### 5. Verify frontend

1. Open `https://<frontend-url>/app/dashboard`: metrics should match seeded backend data.
2. Open `/app/traces`: list should include seeded `trc_...` rows.
3. No “Demo fallback · backend unavailable” banner when backend is healthy (may take a moment if Render was sleeping).

---

## Post-deploy checklist

- [ ] `GET https://<render-backend-url>/health` → database connected
- [ ] `POST https://<render-backend-url>/v1/demo/seed` → success (with `HELIOS_DEMO_MODE=true`)
- [ ] `CORS_ORIGINS` includes exact Vercel URL (scheme + host, no path)
- [ ] Vercel build used `VITE_HELIOS_DEMO_MODE=false` and correct `VITE_API_BASE_URL`
- [ ] Dashboard and traces show live data
- [ ] Set `HELIOS_DEMO_MODE=false` on Render after seeding
- [ ] Update README with real `<frontend-url>` and `<render-backend-url>` (Phase E)

---

## SDK demo against production API

From your machine (repo root):

```bash
python -m venv .venv-demo && source .venv-demo/bin/activate
pip install -r examples/rag_support_bot/requirements.txt
python examples/rag_support_bot/run_demo.py \
  --api-url https://<render-backend-url> \
  --query "Can I export traces to Datadog?"
```

Verify the new trace:

```bash
curl "https://<render-backend-url>/v1/traces?project_slug=rag-support-bot"
```

The script prints a new `trace_id` and a localhost view link; substitute your Vercel `<frontend-url>` when sharing.

---

## CORS troubleshooting

**Symptom:** Browser console shows CORS errors; frontend shows fallback banner.

**Fixes:**

1. Set `CORS_ORIGINS` to the exact frontend origin:
   - `https://your-app.vercel.app` (no trailing path)
   - Include both `www` and apex if you use both
   - For preview deploys, add each preview URL or use localhost during backend-only testing
2. Redeploy/restart the Render service after changing `CORS_ORIGINS`.
3. Confirm `VITE_API_BASE_URL` uses `https://` and matches the Render public URL.
4. Check Render deploy logs for Alembic/uvicorn errors.
5. If requests time out, the free tier may be cold-starting; retry after ~60s.

**Test CORS from terminal:**

```bash
curl -i -H "Origin: https://<frontend-url>" https://<render-backend-url>/health
```

Look for `access-control-allow-origin` in the response headers.

---

## SSL / Postgres notes

- **Render Postgres:** Use the **Internal Database URL** from the Render dashboard for the backend service on Render.
- **Supabase:** Use the connection string from the dashboard; append `?sslmode=require` if you see SSL errors.
- **Local dev:** `docker-compose.dev.yml` uses non-SSL Postgres on port **5433**; unchanged by production setup.

---

## Local Docker Compose (unchanged)

`docker-compose.dev.yml` overrides the container start command and still runs:

```bash
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Port **8000** is fixed in compose; `$PORT` is for Render-style hosts.

---

## Alternative: Railway

Railway works with the same backend Dockerfile and env vars if you have an active plan:

1. Create Railway project → add **PostgreSQL** + **GitHub service** (root directory `backend`).
2. Reference `${{Postgres.DATABASE_URL}}` on the backend service.
3. Set `CORS_ORIGINS`, `HELIOS_DEMO_MODE=true`.
4. Generate a public domain.
5. Dockerfile CMD already runs migrations:  
   `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`

Seed and verify with the same curl commands, substituting your Railway URL for `<render-backend-url>`.

---

## Portfolio scope (intentional limitations)

Helios is a **portfolio MVP**, not production SaaS. After deployment, these remain true:

- **No auth**: `POST /v1/traces` is open; anyone can ingest traces
- **No rate limiting**: public URL can receive abuse/spam traces
- **Demo seed**: when `HELIOS_DEMO_MODE=true`, anyone can call `/v1/demo/seed`
- **Sample-scale metrics**: dashboard/RAG numbers are illustrative
- **Demo-only UI**: create/run buttons show a placeholder notice
- **`/app/experiments`**: static demo data only (not wired to API)
- **No workers, OTel, or billing**
- **Render free tier sleep**: cold starts affect demo responsiveness

Disable demo seed after initial setup; plan auth/rate limiting before any non-portfolio use.

---

## Related docs

- [FRONTEND_BACKEND_INTEGRATION.md](FRONTEND_BACKEND_INTEGRATION.md): demo mode and API wiring
- [SDK_INGESTION.md](SDK_INGESTION.md): Python SDK and RAG demo
- [diagrams/production-deployment.md](../diagrams/production-deployment.md): Mermaid topology
- [diagrams/deployment.md](../diagrams/deployment.md): local dev topology
