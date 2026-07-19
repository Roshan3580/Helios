# Frontend ↔ Backend Integration

## Environment

| Variable                | Default                 | Description                                                                 |
| ----------------------- | ----------------------- | --------------------------------------------------------------------------- |
| `VITE_API_BASE_URL`     | `http://localhost:8000` | Helios FastAPI base URL                                                     |
| `VITE_HELIOS_DEMO_MODE` | `true`                  | Affects **legacy** analytics pages only (RAG, evals, prompts, datasets)     |

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

## Authenticated product pages (Checkpoints 6–7)

### Project selector

Mounted in the app shell (`ProjectSelectionProvider` + `ProjectSelector`):

1. Loads `GET /v2/user/projects` with a WorkOS JWT.
2. Selects the first authorized project by default.
3. Persists **only** the selected project ID in `localStorage` (`helios.selectedProjectId`).
4. Validates the persisted ID against the current authorized list; discards it if unauthorized.
5. Refetches when the active WorkOS organization changes.

Empty state: an administrator must link/create a project for the organization.

### Dashboard

| Route | API |
| ----- | --- |
| `/app/dashboard` | `GET /v2/user/projects/{project_id_or_slug}/dashboard?hours=` |

**Query:** `hours` (default `24`, min `1`, max `720`). Window filters on trace `start_time`.

**Metric definitions:**

| Field | Definition |
| ----- | ---------- |
| Error trace | Stored `error_count > 0` on `otel_traces` |
| Durations | Trace `end_time - start_time` (avg / p50 / p95 via PostgreSQL `percentile_cont`) |
| Tokens | Sum of numeric `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens` on spans; missing or non-numeric values ignored (never estimated; no 75/25 split) |
| Models | Spans with `gen_ai.request.model`, else `gen_ai.response.model` |
| Cost | **Not computed** — no verified stored cost standard |

UI sections: overview cards (traces, error rate, p50/p95, spans, tokens), service health, model usage (empty when no model attrs), recent errors → `/app/traces/{trace_id}`. Time-window selector: 24h / 7d / 30d. **No** silent demo fallback, hardcoded `"acme"`, or legacy `/v1/dashboard/summary`.

### Traces

| Route | API |
| ----- | --- |
| `/app/traces` | `GET /v2/user/projects/{project_id_or_slug}/traces` |
| `/app/traces/:id` | `GET /v2/user/projects/{project_id_or_slug}/traces/{trace_id}` |

Optional list filters: `limit`, `service_name`, `has_errors`.

**Trace list columns:** Trace ID, Service, Root operation, Start time, Duration, Spans, Errors (environment shown in footer / project selector).

**Trace detail:** real OTel summary fields (service, environment, root operation, start/end, duration, span/error counts) plus a waterfall timeline and span inspector for attributes, resource, scope, events, links, and dropped counts.

Fabricated detail panels (fake inputs, RAG chunks, cost breakdowns) are removed from authenticated trace routes. There is **no** silent demo fallback on `/app/traces*` or `/app/dashboard`.

### Deterministic trace analysis (Checkpoint 9)

| Route | API |
| ----- | --- |
| `/app/traces/:id` (panel) | `POST /v2/user/projects/{project_id_or_slug}/analysis/traces/{trace_id}` |

The trace-detail page includes a **Trace analysis** panel backed by the
deterministic evidence engine (see
[ANALYST_EVIDENCE_ENGINE.md](ANALYST_EVIDENCE_ENGINE.md)):

- Explicit **Analyze trace** action (never auto-runs); **Run again** / **Run again**
  reruns the last selected mode.
- Request body accepts optional `rules` and `include_narrative` (default
  `false`). Omitted/null `rules` runs all default `single-trace-v1` rules.
  Empty lists and unknown rule IDs return `422`. Callers cannot send
  provider/model/prompt/temperature fields.
- Response is deterministic (`mode: "deterministic"`), ephemeral (never
  persisted anywhere, including localStorage/sessionStorage), project-scoped,
  and content-excluding: no prompts, completions, tool arguments/outputs,
  documents, secrets, or cost/RAG/citation/hallucination/evaluation claims.
- Findings link to real spans: activating a finding selects the cited span in
  the waterfall and span inspector after validating it against the loaded
  trace (`span:<span_id>` selectors parsed via `src/lib/analyst/span-selectors.ts`).
- Telemetry coverage counts and mandatory analyst limitations are always
  shown; zero findings does not claim the trace is healthy.
- Optional **Generate explanation** requests `include_narrative: true`. The
  UI shows `narrative_status` (`not_requested` / `disabled` / `complete` /
  `failed`). Narrative is disabled by default in Helios environments and
  never required for deterministic analysis. See
  [ADR_005_OPTIONAL_ANALYST_NARRATIVE.md](ADR_005_OPTIONAL_ANALYST_NARRATIVE.md).

### Error handling (authenticated APIs)

| Status | Behavior |
| ------ | -------- |
| `401` | Redirect to `/api/auth/sign-in` with a safe return path |
| `403` | “You do not have access to this organization or project.” (analysis panel: “You do not have access to analyze this project.”) |
| `404` (detail) | “This trace was not found in the selected project.” |
| `422` (analysis) | Safe rule-validation message (contract mismatch; not expected in normal use) |
| Network/5xx | Explicit error panel with Retry (analysis panel: “Trace analysis could not be completed.”) |

## Legacy analytics pages (not yet migrated)

These still use the unauthenticated legacy client and may fall back to demo data
when `VITE_HELIOS_DEMO_MODE` is not `"false"`:

| Route | API |
| ----- | --- |
| `/app/rag-analytics` | `GET /v1/rag/metrics` |
| `/app/evaluations` | `GET /v1/evaluations` |
| `/app/prompts` | `GET /v1/prompts` |
| `/app/datasets` | `GET /v1/datasets` |
| `/app/experiments` | Static / demo UI |
| `/app/settings` | Static mock UI |

Public marketing pages may still show static demo traces outside `/app/*`. The
legacy `src/lib/api/dashboard.ts` client remains for any deferred consumers but
is **not** used by `/app/dashboard`.

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
