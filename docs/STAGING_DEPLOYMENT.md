# Staging deployment contract

> **Boundary:** Checkpoint 14 defines and validates the staging deployment
> contract. It does **not** create Vercel/Render/WorkOS resources and does
> **not** mark staging as deployed.

## Architecture

```text
Fixed Vercel staging hostname
  https://helios-staging.example.vercel.app   (placeholder)
        │  HTTPS + WorkOS AuthKit session / bearer JWT
        ▼
Fixed Render staging API
  https://helios-api-staging.example.onrender.com   (placeholder)
        ├── Render staging PostgreSQL
        ├── WorkOS staging issuer + JWKS (HTTPS)
        └── OpenAI narrative disabled by default
```

Replace placeholder hostnames with the URLs your platforms assign. Prefer a
**fixed** staging deployment over dynamic Vercel preview URLs so WorkOS
redirect URIs remain stable.

## Official guidance reviewed (Jul 2026)

| Source | Decision applied |
|--------|------------------|
| [Vercel: Deploy TanStack Start](https://vercel.com/kb/guide/deploy-a-tanstack-start-app-to-vercel) | Nitro `preset: "vercel"` already in `vite.config.ts`; no ceremonial `vercel.json` |
| [TanStack Start env vars](https://tanstack.com/start/latest/docs/framework/react/guide/environment-variables) | Only non-secrets use `VITE_*`; WorkOS secrets remain unprefixed |
| [Render Blueprint spec](https://render.com/docs/blueprint-spec) | `render.yaml` with `preDeployCommand: alembic upgrade head`, `healthCheckPath: /health/ready`, `$PORT` bind |
| [Render health checks](https://render.com/docs/health-checks) | HTTP readiness path returns 2xx only when DB + migrations are ready |
| [WorkOS AuthKit TanStack Start](https://github.com/workos/authkit-tanstack-start/) | `WORKOS_CLIENT_ID`, `WORKOS_API_KEY`, `WORKOS_REDIRECT_URI`, `WORKOS_COOKIE_PASSWORD` (≥32); staging vs production isolation |

## Health endpoints

| Path | Auth | DB | Purpose |
|------|------|----|---------|
| `GET /health/live` | none | no | Process liveness |
| `GET /health/ready` | none | yes | DB + `alembic_version` present |
| `GET /health` | none | yes | Legacy combined probe |

## Migration contract

- Render `preDeployCommand`: `alembic upgrade head` (once per deploy)
- Start command uses **one** uvicorn worker (`--workers 1`)
- Operator check: `python -m app.cli.deployment_check` / `--config-only` / `--strict-migrations`
- Alembic head remains `004_human_identity` (no Checkpoint 14 migration)
- Never run `alembic downgrade` automatically

## CORS

- Exact origins from `CORS_ORIGINS`
- Loopback regex only when `HELIOS_ENVIRONMENT` is local/test/e2e **or** `HELIOS_E2E_TEST_MODE=true`
- Staging forbids `*`, localhost, and HTTP origins
- Methods/headers limited to canonical browser needs (`Authorization`, `Content-Type`, …)

## E2E prohibition

`HELIOS_E2E_TEST_MODE` and `VITE_HELIOS_E2E_TEST_MODE` must be `false` in staging.
`/api/e2e/session` and `/v2/e2e/*` must remain unavailable.

## Legacy/demo API prohibition (Checkpoint 18)

`HELIOS_DEMO_MODE` must be `false` in staging (same mechanism and same
`app.main.lifespan` startup check as the E2E prohibition above). When true,
the backend mounts eight unauthenticated legacy routers (`/v1/projects`,
`/v1/traces`, `/v1/dashboard`, `/v1/rag`, `/v1/evaluations`, `/v1/prompts`,
`/v1/datasets`, `/v1/demo/seed`) — this was release-candidate finding L1.
`python -m app.cli.deployment_check --config-only` fails with
`demo_mode_forbidden` if staging sets it true. Canonical `POST /v1/otlp/traces`
and all `/v2/*` routes are mounted unconditionally and are never affected by
this flag.

## Deploy order (manual)

1. Create staging PostgreSQL  
2. Create backend service; set env; apply Blueprint or equivalent  
3. Let `preDeployCommand` migrate  
4. Verify `/health/live` and `/health/ready`  
5. Configure WorkOS **staging** redirect URI to fixed frontend callback  
6. Create Vercel staging project; set server + `VITE_*` vars  
7. Deploy frontend  
8. Set exact `CORS_ORIGINS`; redeploy backend if needed  
9. Run `scripts/smoke-staging.sh`  
10. Manually verify WorkOS login → project → key → OTLP → UI → sign-out  
11. Do **not** auto-promote to production  

## Smoke test

```bash
export HELIOS_STAGING_FRONTEND_URL=https://helios-staging.example.vercel.app
export HELIOS_STAGING_API_URL=https://helios-api-staging.example.onrender.com
# optional: export HELIOS_STAGING_PROJECT_KEY=…   # never commit
bash scripts/smoke-staging.sh
```

## Rollback

- **Frontend:** redeploy known-good Vercel staging deployment; keep redirect URI compatible  
- **Backend:** redeploy prior commit; do not auto-downgrade DB; confirm readiness  
- **Database:** forward-fix only; Checkpoint 14 adds no migration  
- **Secret incident:** rotate WorkOS API key, cookie password, project keys, OpenAI (if enabled), DB credential; redeploy; invalidate sessions  

## Operator preflight (WorkOS)

- [ ] Staging environment (not production)  
- [ ] Redirect URI = `https://<fixed-frontend>/api/auth/callback`  
- [ ] Sign-in endpoint = `https://<fixed-frontend>/api/auth/sign-in`  
- [ ] Sign-out redirect = frontend origin `/`  
- [ ] Cookie password ≥ 32 characters  
- [ ] Backend `WORKOS_CLIENT_ID` / issuer / JWKS match staging client  
- [ ] Organization linked via admin CLI before self-serve  

## Related docs

- [DEPLOYMENT_ENVIRONMENT_MATRIX.md](./DEPLOYMENT_ENVIRONMENT_MATRIX.md)
- [RELEASE_READINESS.md](./RELEASE_READINESS.md)
- [BROWSER_E2E_RELEASE_GATE.md](./BROWSER_E2E_RELEASE_GATE.md)
- [DEPLOYMENT.md](./DEPLOYMENT.md) (legacy portfolio notes — prefer this staging contract for v2)
