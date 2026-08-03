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
| Backend   | Render **Free** web service `helios-api-beta` | Free | `https://helios-0cqu.onrender.com`, built from branch `main` |
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
| `VITE_API_BASE_URL`        | `https://helios-0cqu.onrender.com` |
| `VITE_HELIOS_ENVIRONMENT`  | `staging` |
| `VITE_HELIOS_DEMO_MODE`    | `false` |
| `VITE_HELIOS_E2E_TEST_MODE`| `false` |

Server-only (set in the Vercel dashboard; **never** `VITE_*`):

| Variable                | Value |
|-------------------------|-------|
| `WORKOS_CLIENT_ID`      | current Helios staging application Client ID |
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
| `WORKOS_CLIENT_ID`                | current Helios staging application Client ID; same as Vercel |
| `WORKOS_ISSUER`                   | leave unset for standard or multi-application mode; set only for an exact custom HTTPS issuer |
| `WORKOS_ISSUER_CLIENT_ID`         | set to the default WorkOS application only for multi-application mode; otherwise unset; Render/backend-only, never Vercel or `VITE_*` |
| `WORKOS_JWKS_URL`                 | leave unset → derives `https://api.workos.com/sso/jwks/<client_id>` |

`OPENAI_API_KEY` is intentionally **unset** — narrative stays disabled.

The backend runs under the hardened `staging` contract: startup fails closed if
`HELIOS_DEMO_MODE=true`, if `HELIOS_E2E_TEST_MODE=true`, if CORS is a wildcard or
loopback, or if the environment value is unknown (see
`app/deployment_validation.py`).

## Hosted sign-in troubleshooting

**Symptom:** a clean WorkOS sign-in loads the shell, the user's name renders, and
the UI immediately shows "Your session has expired" — while Render logs show only
`/health/ready` and no `/v2/user/me`.

**This is a frontend token-readiness bug, not a backend, JWT, or WorkOS problem.**
No backend request was ever attempted, so nothing in Render, the verifier, the
issuer configuration, or the database is implicated. Diagnose in this order:

1. **Did Render receive `/v2/user/me` at all?** If not, the failure is entirely
   client-side and pre-backend. Do not change backend env vars, `WORKOS_ISSUER`,
   `WORKOS_JWKS_URL`, or `CORS_ORIGINS` — none of them are involved.
2. **Did the browser issue a same-origin server-function RPC before the panel
   appeared?** If not, the client short-circuited before asking WorkOS for a
   token. The SDK's `getAccessToken()` returns nothing — without any network
   call — while the user is still unresolved.
3. **Does the user's name render?** If yes, the WorkOS session cookie *was*
   delivered and the callback succeeded; the session is valid.

The fix (Checkpoint 27) is that the client distinguishes *token initializing*
from *token unavailable*; see the readiness table in
`docs/ADR_004_WORKOS_HUMAN_AUTH.md`. A genuine backend 401 looks different: Render
logs the request, and recovery is only entered after one refresh and one retry.

### The request reached the verifier: reading the safe reason code

**Symptom:** Render logs show a successful CORS preflight *and* an authenticated
GET that returns 401 — for example:

```
OPTIONS /v2/user/me      200
OPTIONS /v2/user/projects 200
GET     /v2/user/me      401
GET     /v2/user/projects 401
```

A successful preflight plus an authenticated `GET` returning 401 means **the
request reached the backend verifier**. This is no longer a readiness or CORS
problem: a token was presented and rejected. The cause is now determinable.

Search the Render logs for:

```
human auth rejected
```

Each rejection emits exactly one line, of exactly this shape:

```
human auth rejected: reason=<SAFE_REASON> status=<401|403> path=<ROUTE>
```

Only the safe reason code, the HTTP status, and the matched application route
path are emitted. The JWT, its header and claims, the Authorization header,
cookies, the Client ID value, user/organization/session identifiers, the issuer
URL, the JWKS URL, and exception text are never logged — the log formatter drops
exception and stack detail structurally, not merely by convention.

On startup each worker also emits one non-secret configuration line:

```
human auth verifier configured: client_id_present=true issuer_client_id_present=true issuer_mode=multi_application jwks_mode=derived environment=staging
```

`issuer_mode` is `derived_standard_set`, `multi_application`, or `explicit`;
`jwks_mode` is `derived` or `explicit`. Presence fields are booleans only. No
URL, hostname, or Client ID value appears. If this line is absent, the deployed
build predates Checkpoint 28 (or startup aborted — check for
`Helios deployment contract failed`).

**The reason code determines the next action. Change one thing, then re-test
once:**

| `reason=` | Meaning | Next action |
|---|---|---|
| `auth_missing_token` | No bearer credential arrived | Inspect whether the frontend attached an `Authorization` header at all |
| `auth_expired_token` | Signature valid, `exp` passed | Inspect the session refresh lifecycle |
| `auth_invalid_issuer` | `iss` matched neither accepted value | See "Accepted issuer values" below before changing anything |
| `auth_invalid_client_id` | Token minted for a different WorkOS application | Verify Vercel, Render, and WorkOS application parity |
| `auth_invalid_signature` | Signature, `kid`, algorithm, or JWT structure rejected | Verify WorkOS environment / JWKS parity |
| `auth_jwks_failure` | JWKS document could not be fetched | Verify outbound network access and WorkOS availability |
| `auth_missing_org` | Verified user with no usable active organization (403) | Use workspace onboarding or organization selection |
| `auth_not_configured` | Backend WorkOS settings absent | Restore the backend WorkOS configuration |
| `auth_invalid_token` | Required claims missing | Verify the token is a WorkOS **access** token, not another token type |
| `auth_missing_subject` | No `sub` claim | Verify the token type and WorkOS application configuration |
| `auth_rejected` | Unmapped internal reason (fallback) | Report it: the mapping needs a new explicit case |

Do not retry sign-in repeatedly while diagnosing. One rejection produces one log
line; repeated attempts only make the log harder to read, and WorkOS rate-limits
sign-in (which surfaces separately as a bounded 429 panel, never a retry loop).

> Note: uvicorn's own access logger echoes the full request line, including any
> query string, as every web server does. Helios never places a credential in a
> query string — the browser client sends the token in the `Authorization` header
> only, and the Helios diagnostic line carries the route path without its query
> string.

### Accepted issuer values

Helios selects one of three mutually exclusive issuer modes from validated
backend configuration:

```
https://api.workos.com
https://api.workos.com/
https://api.workos.com/user_management/<default_client_id>
```

In `derived_standard_set`, both issuer variables are unset and only the two API
roots are accepted. In `multi_application`, `WORKOS_ISSUER_CLIENT_ID` is set,
`WORKOS_ISSUER` is unset, and only the one no-trailing-slash user-management
issuer is accepted. In `explicit`, `WORKOS_ISSUER_CLIENT_ID` is unset and only
the exact configured HTTPS issuer is accepted. Setting both fails startup.

All modes use exact full-string equality. Helios performs no normalization and
no prefix, suffix, substring, regex, subdomain, path, or wildcard matching. In
multi-application mode all of the following stay rejected:

```
https://api.workos.com/user_management/<other_client_id>
https://api.workos.com/user_management/<default_client_id>/
https://api.workos.com/user_management/
https://api.workos.com/anything
https://api.workos.com//
http://api.workos.com
https://evil.api.workos.com
https://api.workos.com.evil.example
```

Accepting the configured multi-application issuer does not weaken tenancy:
isolation comes from the separately validated `client_id` claim and the
application-specific JWKS at `/sso/jwks/<client_id>` — both unchanged. The
issuer may even embed a different (default-app) client id than Helios's own.

If you see `auth_invalid_issuer`:

1. **Confirm the startup line reports the intended mode.** Standard deployments
   use `derived_standard_set`; the confirmed hosted shape uses
   `multi_application`; custom issuers use `explicit`.
2. **If Helios is a secondary WorkOS application**, set
   `WORKOS_ISSUER_CLIENT_ID` to the environment's default application client id
   (the id embedded in `iss`). Do not put that value into `WORKOS_CLIENT_ID`.
3. **Do not add a trailing slash to "fix" multi-application mode.** Its issuer
   is intentionally the single no-trailing-slash value.
4. Set `WORKOS_ISSUER` only for a deliberately configured custom WorkOS auth
   domain. It is then an exact contract: `https://auth.example.com` does **not**
   also accept `https://auth.example.com/`.

FastAPI does not need `WORKOS_API_KEY`. JWKS and token `client_id` validation
always use `WORKOS_CLIENT_ID`; only multi-app issuer derivation uses
`WORKOS_ISSUER_CLIENT_ID`. Never put real identifiers in committed files.

## Free-tier limitations

- **Cold starts:** the Render Free backend sleeps after inactivity and can take
  up to ~1 minute to wake. Authenticated pages surface a bounded "Helios Beta is
  waking up" notice with a Retry button and never fall back to demo data.
- **No uptime guarantee / no SLA.**
- **Limited database capacity** on the free PostgreSQL tier.
- **No sensitive or production workloads.**
- **No real OpenAI narrative** (deterministic analysis only).
- Invited beta, not a production release.

The confirmed deployment is a production-capable hosted beta. Run the complete
[hosted beta smoke test](./HOSTED_BETA_SMOKE_TEST.md) for each release candidate.

## Deferred release work

- Public Python SDK publication
- Public TypeScript SDK publication
- Self-serve workspace onboarding
- Usage limits and retention
- Operational recovery hardening
- Separate demo database restoration
- Full em-dash removal across production and demo user-facing copy

These tasks are outside this checkpoint. This source change does not deploy,
publish packages, modify hosted configuration, or touch the public demo.
