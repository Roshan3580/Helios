# Self-serve project onboarding

Helios Checkpoint 12 adds human-authenticated project creation and project
API-key management so members of a linked WorkOS organization can start
sending telemetry without the administrative CLI.

## Prerequisites

- The caller authenticates with a WorkOS access token
  (`Authorization: Bearer <token>`).
- The JWT `org_id` must already be linked to a local Helios organization
  (admin CLI: `python -m app.cli.organizations create …`). Organizations are
  still not auto-created from arbitrary WorkOS org IDs.
- Project API keys remain machine credentials. Human routes never accept
  `hel_proj_*` keys for authorization.

## Access boundary

Any authenticated member of the **active linked WorkOS organization** can:

- list and create projects in that organization,
- list, create, and revoke project API keys for those projects.

Helios does **not** implement per-project roles, administrator-only key
management, or audit history in this checkpoint. Finer-grained RBAC is
deferred.

Browser release-gate coverage for this flow lives in
[BROWSER_E2E_RELEASE_GATE.md](BROWSER_E2E_RELEASE_GATE.md) (Chromium + loopback
JWKS; not a substitute for real WorkOS staging login).

## Project creation

```http
POST /v2/user/projects
```

Request (extra fields forbidden):

```json
{ "name": "Production Agent", "slug": "production-agent", "environment": "production" }
```

- `name` and `slug` are required (trimmed).
- `environment` is optional and constrained to
  `production | staging | development | test` (default `production`).
- Slugs are lowercase ASCII letters/numbers/hyphens, no leading/trailing or
  consecutive hyphens, max 128 characters.
- Slug uniqueness is currently **global** (`projects.slug` UNIQUE). The same
  slug cannot be reused in another organization until a future migration
  changes that constraint.
- Response matches `GET /v2/user/projects` (`UserProjectRead`): id, slug,
  name, environment. No secrets.

Duplicate slug → `409` with a generic message (no constraint names).

## Project API keys

```http
GET  /v2/user/projects/{project_ref}/api-keys
POST /v2/user/projects/{project_ref}/api-keys
POST /v2/user/projects/{project_ref}/api-keys/{key_id}/revoke
```

`project_ref` may be project UUID or slug, scoped to the caller’s organization.
Cross-org or missing project → `404`.

### Create

```json
{ "name": "Local development", "scopes": ["traces:ingest", "traces:read"] }
```

Scopes must be from the existing registry:

- `traces:ingest` — OTLP ingestion (`POST /v1/otlp/traces`)
- `traces:read` — machine reads (`GET /v2/traces*`)

Response:

```json
{
  "key": { "id": "…", "name": "…", "key_identifier": "hel_proj_<prefix>…", "scopes": ["…"], "created_at": "…", "revoked_at": null, "status": "active" },
  "plaintext_key": "hel_proj_<prefix>_<secret>"
}
```

`plaintext_key` appears **only** in this successful creation response.

### Storage and reveal rules

- Database stores `key_prefix` (non-secret lookup) and `key_hash` (SHA-256 of
  the full token). Plaintext is never persisted.
- List and revoke responses contain only redacted metadata (`key_identifier`,
  never the hash or full token).
- The browser may hold plaintext in React memory for a one-time reveal only.
  It must not be written to localStorage, sessionStorage, IndexedDB, cookies,
  URLs, logs, analytics, or error messages.
- After the reveal is dismissed or lost, the key is unrecoverable — create
  another key.

### Revoke

Revocation sets `revoked_at` and is **idempotent**. Rows are retained.
Revoked keys immediately fail machine authentication.

## Onboarding UI

Canonical routes:

- `/app/getting-started` — create first project, checklist, SDK/OTLP
  instructions, telemetry check
- `/app/settings/api-keys` — manage keys for the selected project
- `/app/settings` — project settings hub (no demo keys)

Zero-project pages (Dashboard, Traces, Insights) link to Getting started and
do not invent demo projects or `acme` defaults.

Telemetry arrival is checked with an explicit **Check for traces** action
that calls `GET /v2/user/projects/{ref}/traces?limit=1`. There is no
background poller.

## Verified SDK / OTLP setup

Instructions on Getting started match the repository:

```bash
pip install -e "sdk/python[otel,openai]"
export HELIOS_API_KEY=<YOUR_HELIOS_PROJECT_KEY>
export HELIOS_ENDPOINT=http://localhost:8000
export HELIOS_SERVICE_NAME=my-agent
```

```python
from helios_sdk import Helios
helios = Helios.configure(api_key=…, service_name=…, endpoint=…)
helios.instrument_openai()
```

Raw OTLP:

```http
POST {HELIOS_ENDPOINT}/v1/otlp/traces
Authorization: Bearer <project key>
Content-Type: application/x-protobuf
```

## Security limitations (intentional)

- No plaintext key recovery
- No encrypted secret storage
- No automatic key rotation
- No key-usage timestamps in the UI (column may exist for machine auth
  bookkeeping but is not surfaced here)
- No audit-log table
- No per-project RBAC
- No background onboarding worker

## CLI still available

Admin operators may continue to use:

- `python -m app.cli.organizations …`
- `python -m app.cli.api_keys …`

Self-serve HTTP APIs are the primary path for ordinary authenticated users.
