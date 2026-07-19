# Frontend ↔ Backend Integration

## Environment

| Variable                | Default                 | Description                                                                 |
| ----------------------- | ----------------------- | --------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`     | `http://localhost:8000` | Helios FastAPI base URL                                                     |
| `VITE_HELIOS_DEMO_MODE` | `true`                  | Affects **legacy** analytics pages only (dashboard, RAG, evals, etc.)       |

WorkOS human authentication uses **server-only** env vars (`WORKOS_CLIENT_ID`,
`WORKOS_API_KEY`, `WORKOS_COOKIE_PASSWORD`, `WORKOS_REDIRECT_URI`). Never put
those behind `VITE_*`. See [ADR 004](ADR_004_WORKOS_HUMAN_AUTH.md).

## Credential boundary

| Caller | Credential | Routes |
| ------ | ---------- | ------ |
| Browser (authenticated) | WorkOS access token (`Authorization: Bearer`) | `/v2/user/*` |
| SDK / services | Project API key `hel_proj_*` | `/v1/otlp/traces`, `/v2/traces*` |
| Legacy analytics (temporary) | None | `/v1/dashboard`, `/v1/rag`, … |

The browser **never** sends project API keys. Tokens are obtained fresh via
`useAccessToken().getAccessToken()` immediately before each authenticated
request and are not written to localStorage, sessionStorage, query strings, or
error messages.

## Authenticated product pages (Checkpoint 6)

### Project selector

Mounted in the app shell (`ProjectSelectionProvider` + `ProjectSelector`):

1. Loads `GET /v2/user/projects` with a WorkOS JWT.
2. Selects the first authorized project by default.
3. Persists **only** the selected project ID in `localStorage` (`helios.selectedProjectId`).
4. Validates the persisted ID against the current authorized list; discards it if unauthorized.
5. Refetches when the active WorkOS organization changes.

Empty state: an administrator must link/create a project for the organization.

### Traces

| Route | API |
| ----- | --- |
| `/app/traces` | `GET /v2/user/projects/{project_id_or_slug}/traces` |
| `/app/traces/:id` | `GET /v2/user/projects/{project_id_or_slug}/traces/{trace_id}` |

Optional list filters: `limit`, `service_name`, `has_errors`.

**Trace list columns:** Trace ID, Service, Root operation, Start time, Duration, Spans, Errors (environment shown in footer / project selector).

**Trace detail:** real OTel summary fields (service, environment, root operation, start/end, duration, span/error counts) plus a waterfall timeline and span inspector for attributes, resource, scope, events, links, and dropped counts.

Fabricated detail panels (fake inputs, RAG chunks, cost breakdowns) are removed from authenticated trace routes. There is **no** silent demo fallback on `/app/traces*`.

### Error handling (authenticated APIs)

| Status | Behavior |
| ------ | -------- |
| `401` | Redirect to `/api/auth/sign-in` with a safe return path |
| `403` | “You do not have access to this organization or project.” |
| `404` (detail) | “This trace was not found in the selected project.” |
| Network/5xx | Explicit error panel with Retry |

## Legacy analytics pages (not yet migrated)

These still use the unauthenticated legacy client and may fall back to demo data
when `VITE_HELIOS_DEMO_MODE` is not `"false"`:

| Route | API |
| ----- | --- |
| `/app/dashboard` | `GET /v1/dashboard/summary`, `GET /v1/prompts` |
| `/app/rag-analytics` | `GET /v1/rag/metrics` |
| `/app/evaluations` | `GET /v1/evaluations` |
| `/app/prompts` | `GET /v1/prompts` |
| `/app/datasets` | `GET /v1/datasets` |

Settings remains static mock UI. Public marketing pages may still show static
demo traces outside `/app/*`.

## Status mapping (legacy analytics only)

| Backend   | Frontend  |
| --------- | --------- |
| `success` | `success` |
| `warning` | `warn`    |
| `error`   | `error`   |

OTel trace UI uses OpenTelemetry status codes (`UNSET` / `OK` / `ERROR`) instead.

## Local verification

```bash
# Backend (with WorkOS JWT verification configured — see ADR 004)
docker compose -f docker-compose.dev.yml up -d postgres
cd backend && source .venv/bin/activate
export DATABASE_URL=postgresql://helios:helios@localhost:5433/helios
alembic upgrade head && uvicorn app.main:app --reload --port 8000

# Frontend (requires WORKOS_* server env for /app/*)
bun dev
```

Sign in via WorkOS, select a project, and open `/app/traces`. Hosted WorkOS
development credentials are required for a real browser login; CI builds without
them.
