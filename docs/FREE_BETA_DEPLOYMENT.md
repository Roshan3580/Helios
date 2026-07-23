# Free invited-beta deployment

This document describes how to run the **real Helios product** (WorkOS human
authentication + project API keys + OTLP ingestion) for a small set of invited
testers on **zero-cost infrastructure**.

> The free beta is **not** an SLA-backed production service. It exists so
> invited testers can exercise the real onboarding and telemetry flow. Do not
> put sensitive or production workloads on it. See "Free-tier limitations".

Checkpoint 24 removed the manual database step from onboarding: a verified
WorkOS organization is mapped to a local Helios organization automatically and
tenant-safely on first sign-in (see `app/services/identity_bootstrap.py`). An
invited tester never needs an administrator to run SQL or the org CLI.

## Architecture

| Layer     | Resource                                   | Cost | Notes |
|-----------|--------------------------------------------|------|-------|
| Frontend  | Existing Vercel project `helios-staging`   | Free | `https://helios-staging-tau.vercel.app` |
| Auth      | WorkOS **Staging** environment             | Free | Invited testers only |
| Backend   | **New** Render **Free** web service `helios-api-beta` | Free | Built from branch `main` |
| Database  | **One** external free PostgreSQL (e.g. Neon free tier) | Free | Beta-only; not shared with demo/prod |

Separation from other environments:

- The **public synthetic demo** lives on branch `demo-v1`
  (`helios-alpha-nine.vercel.app` + `helios-backend`). It is untouched by the
  beta and never shares a database with it.
- The **paid dedicated staging** blueprint (`render.yaml`, service
  `helios-api-staging`) is a separate, paid contract. The free beta does **not**
  use `render.yaml` because that blueprint requests paid resources.
- No OpenAI / narrative provider is configured in the beta.

## Why no Render Blueprint for the beta

The committed `render.yaml` describes the paid dedicated staging service
(`helios-api-staging`, plan `starter`, a managed Render Postgres). Applying it
would provision paid resources. The free beta is therefore configured
**manually** in the Render dashboard as a Free service pointed at an external
free PostgreSQL. `render.yaml` is intentionally left unchanged.

## Manual Render Free service configuration (`helios-api-beta`)

| Setting          | Value                                                              |
|------------------|-------------------------------------------------------------------|
| Name             | `helios-api-beta`                                                  |
| Repository       | `Roshan3580/Helios`                                               |
| Branch           | `main`                                                            |
| Root directory   | `backend`                                                         |
| Runtime          | Python                                                            |
| Plan             | Free                                                              |
| Build command    | `pip install -r requirements.txt`                                |
| Start command    | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1`    |
| Health check     | `/health/ready`                                                  |

Because the beta uses an external database (not a Render Blueprint), run the
Alembic migration **manually before any schema-changing deploy** (there is no
`preDeployCommand` on this manually-created service):

```
# From a checkout of the deployed commit, against the external DATABASE_URL:
cd backend
DATABASE_URL='<external PostgreSQL URL>' alembic upgrade head
```

The external database must reach Alembic head **`004_human_identity`**.
Checkpoint 24 adds **no** migration (the required uniqueness constraints —
`uq_users_workos_user_id`, `uq_organizations_workos_org_id`,
`uq_organizations_slug` — already exist as of `004_human_identity`), so the head
is unchanged.

## Environment-variable matrix (names only — never commit secrets)

See `.env.beta.example` for the committed placeholder file.

### Frontend (Vercel `helios-staging`)

Browser-public (`VITE_*`, non-secret):

| Variable                   | Value |
|----------------------------|-------|
| `VITE_API_BASE_URL`        | `https://helios-api-beta.onrender.com` |
| `VITE_HELIOS_ENVIRONMENT`  | `staging` |
| `VITE_HELIOS_DEMO_MODE`    | `false` |
| `VITE_HELIOS_E2E_TEST_MODE`| `false` |

Server-only (set in the Vercel dashboard; **never** `VITE_*`):

| Variable                | Value |
|-------------------------|-------|
| `WORKOS_CLIENT_ID`      | staging client id |
| `WORKOS_API_KEY`        | server-only staging API key |
| `WORKOS_REDIRECT_URI`   | `https://helios-staging-tau.vercel.app/api/auth/callback` |
| `WORKOS_COOKIE_PASSWORD`| random secret, ≥ 32 characters |

### Backend (Render Free `helios-api-beta`)

| Variable                          | Value |
|-----------------------------------|-------|
| `PYTHON_VERSION`                  | `3.12.8` |
| `HELIOS_ENVIRONMENT`              | `staging` |
| `HELIOS_DEMO_MODE`                | `false` |
| `HELIOS_E2E_TEST_MODE`            | `false` |
| `HELIOS_ANALYST_NARRATIVE_ENABLED`| `false` |
| `HELIOS_ANALYST_ALLOW_THIRD_PARTY`| `false` |
| `DATABASE_URL`                    | external PostgreSQL URL (secret) |
| `CORS_ORIGINS`                    | `https://helios-staging-tau.vercel.app` (exact; no wildcard) |
| `WORKOS_CLIENT_ID`                | same staging client id |
| `WORKOS_ISSUER`                   | derived or explicit issuer |
| `WORKOS_JWKS_URL`                 | derived or explicit JWKS URL |

`OPENAI_API_KEY` is intentionally **unset** — narrative stays disabled.

The backend runs under the hardened `staging` contract: startup fails closed if
`HELIOS_DEMO_MODE=true`, if `HELIOS_E2E_TEST_MODE=true`, if CORS is a wildcard or
loopback, or if the environment value is unknown (see
`app/deployment_validation.py`).

## Free-tier limitations

- **Cold starts:** the Render Free backend sleeps after inactivity and can take
  up to ~1 minute to wake. Authenticated pages surface a bounded "Helios Beta is
  waking up" notice with a Retry button and never fall back to demo data.
- **No uptime guarantee / no SLA.**
- **Limited database capacity** on the free PostgreSQL tier.
- **No sensitive or production workloads.**
- **No real OpenAI narrative** (deterministic analysis only).
- Invited beta, not a production release.

## Not in this checkpoint

Billing, automatic trace retention, SDK publication, and per-project RBAC are
out of scope. This checkpoint is source-only: it does not deploy, publish, or
touch the public demo.
