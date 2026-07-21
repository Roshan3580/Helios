# Deployment environment matrix

Authoritative classification of Helios environment variables for local, E2E,
staging, and production. Placeholders only — never commit real secrets.

| Variable | Runtime | Public/Secret | Required | Staging form | Validation |
|----------|---------|---------------|----------|--------------|------------|
| `VITE_API_BASE_URL` | Frontend build | Public | Yes (staging) | `https://…onrender.com` | HTTPS; no credentials/query |
| `VITE_HELIOS_DEMO_MODE` | Frontend build | Public | Yes | `false` | Boolean string |
| `VITE_HELIOS_ENVIRONMENT` | Frontend build | Public | Recommended | `staging` | Drives URL HTTPS checks |
| `VITE_HELIOS_E2E_TEST_MODE` | Frontend build | Public boolean | Must be false | `false` | Forbidden `true` in staging |
| `WORKOS_CLIENT_ID` | Frontend server + backend | Secret-ish ID | Yes (staging) | staging client | Match issuer/JWKS |
| `WORKOS_API_KEY` | Frontend server only | Secret | Yes (AuthKit) | `sk_test_…` | Never `VITE_*` |
| `WORKOS_REDIRECT_URI` | Frontend server | Public URL | Yes | `https://…/api/auth/callback` | HTTPS; fixed origin |
| `WORKOS_COOKIE_PASSWORD` | Frontend server | Secret | Yes | ≥32 chars | Never `VITE_*` |
| `WORKOS_COOKIE_SAMESITE` | Frontend server | Config | Optional | `lax` | AuthKit default |
| `WORKOS_COOKIE_NAME` | Frontend server | Config | Optional | `wos-session` | AuthKit default |
| `WORKOS_COOKIE_MAX_AGE` | Frontend server | Config | Optional | seconds | AuthKit default |
| `WORKOS_ISSUER` | Backend | Public URL | Yes (or derive) | HTTPS WorkOS | No loopback in staging |
| `WORKOS_JWKS_URL` | Backend | Public URL | Yes (or derive) | HTTPS WorkOS | No loopback in staging |
| `DATABASE_URL` | Backend | Secret | Yes | Render internal URL | Not `helios_test` |
| `CORS_ORIGINS` | Backend | Public list | Yes | Exact HTTPS origin | No `*`, no localhost |
| `HELIOS_ENVIRONMENT` | Backend (+ docs) | Public | Yes | `staging` | Enum |
| `HELIOS_DEMO_MODE` | Backend | Config | Yes | `false` | Startup reject if true (mounts unauthenticated legacy `/v1` routers) |
| `HELIOS_ANALYST_NARRATIVE_ENABLED` | Backend | Config | Default false | `false` | — |
| `HELIOS_ANALYST_ALLOW_THIRD_PARTY` | Backend | Config | Default false | `false` | — |
| `HELIOS_ANALYST_PROVIDER` | Backend | Config | If narrative | `openai` | Requires key if enabled |
| `HELIOS_ANALYST_MODEL` | Backend | Config | If narrative | model id | — |
| `OPENAI_API_KEY` | Backend | Secret | Only if narrative on | unset by default | Never `VITE_*` |
| `HELIOS_E2E_TEST_MODE` | Backend / frontend server | Flag | Forbidden staging | `false` | Startup reject if true |
| `HELIOS_E2E_ACCESS_TOKEN` | E2E only | Secret | E2E only | unset | Forbidden staging |
| `HELIOS_E2E_*` (org/user/jwks) | E2E only | Test | E2E only | unset | Forbidden staging |
| `HELIOS_STAGING_*` | Operator smoke shell | Mixed | Smoke only | Operator-provided | Not platform env |

## Forbidden in staging/production

- Any `HELIOS_E2E_*` enablement or access token  
- `HELIOS_DEMO_MODE=true` (mounts unauthenticated legacy `/v1` routers — Checkpoint 18)  
- Wildcard CORS  
- Loopback WorkOS issuer/JWKS  
- Server secrets in `VITE_*`  
- Real credentials in git  

## Examples

- Local defaults: `.env.example`  
- E2E harness: `.env.e2e.example`  
- Staging placeholders: `.env.staging.example`  
