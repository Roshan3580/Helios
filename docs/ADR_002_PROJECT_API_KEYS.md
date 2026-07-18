# ADR 002: Project-Scoped API Keys for Canonical Telemetry (Helios v2)

Status: Accepted · Branch: `helios-v2-otel-foundation` · Supersedes the
project-header scoping described in [ADR 001](ADR_001_OTLP_TRACE_FOUNDATION.md).

## Context

ADR 001 shipped the canonical v2 path (`POST /v1/otlp/traces`, `GET /v2/traces`)
scoped only by a caller-supplied `X-Helios-Project-Slug` header / `project_slug`
query parameter. That is a stopgap, not a security control: any caller can
name any project, read any project's traces, and create projects by ingesting.
This checkpoint replaces trust-based scoping with authenticated project keys.

## Decision

### Canonical telemetry requires a project API key

Both canonical routes require:

```
Authorization: Bearer <project-api-key>
```

with the appropriate scope. Unauthenticated or under-scoped requests are
rejected before any telemetry is read or written.

### The key determines the project; callers cannot choose it

The authenticated key belongs to exactly one project, and that binding is the
sole source of project scope:

- Ingestion derives the project from the key. The obsolete
  `X-Helios-Project-Slug` header is removed and cannot redirect ingestion.
  `X-Helios-Environment` remains an optional telemetry environment fallback.
- Reads no longer accept `project_slug`. The parameter is removed from the
  endpoint signature, so a stray `?project_slug=` is ignored, and a trace in
  another project is a 404 — indistinguishable from a missing trace.

This makes cross-project access structurally impossible rather than
policy-enforced.

### Plaintext keys are never persisted

Token format:

```
hel_proj_<lookup>_<secret>
```

- `<lookup>`: 16 hex chars, non-secret, the unique DB lookup prefix (also
  shown in listings for identification).
- `<secret>`: `secrets.token_urlsafe(32)` — at least 256 bits of entropy.

Storage keeps only `key_prefix` (the lookup) and `key_hash` =
`sha256(full token)`. The complete token is returned once at creation and is
never persisted or logged. The secret is never stored separately.

**Lookup strategy:** parse the lookup prefix from the presented token, select
the single row by `key_prefix` (unique constraint), then compare
`sha256(token)` against the stored hash with `hmac.compare_digest`
(constant-time).

**Why SHA-256, not bcrypt/argon2:** these are 256-bit cryptographically random
tokens, not human passwords. Password-hash work factors defend low-entropy
secrets against brute force; a 256-bit random token is infeasible to
brute-force regardless, so a fast deterministic digest is correct and supports
constant-time comparison.

### Scopes

Two scopes this checkpoint, stored as a JSONB string array (no PostgreSQL
enum, so new scope strings need no migration; validated in the application
layer):

- `traces:ingest` — required by `POST /v1/otlp/traces`
- `traces:read` — required by `GET /v2/traces*`

A valid key lacking the required scope returns **403** (distinct from the
**401** for credential problems).

### Revocation and expiration

- `revoked_at`: set by the admin CLI; a revoked key authenticates as invalid.
  Revocation preserves historical metadata (no row deletion).
- `expires_at`: optional; a key at/after its expiry authenticates as invalid.
- `last_used_at`: updated after each successful authentication in a **dedicated
  short-lived session committed independently** of the request session, so
  read requests (which never commit) still record usage and an ingest rollback
  never reverts the audit write.

### Error behavior

- Missing/malformed/unknown/mismatched/revoked/expired credentials → **401**
  with `WWW-Authenticate: Bearer` and a single generic message
  (`"invalid authentication credentials"`). Responses never reveal whether a
  prefix exists or whether a key was revoked vs expired.
- Valid key, missing scope → **403**.
- Internal failure categories are logged with a non-secret reason; tokens,
  `Authorization` headers, and full prefixes are never logged. No database or
  hashing internals reach clients.

### Deferrals (unchanged from ADR 001 intent)

- **Users, organizations, browser sessions, OAuth/JWT login:** out of scope.
  This checkpoint creates *service-level* project keys only, managed by an
  administrative CLI. Browser/user auth is a later batch; keys must never be
  placed in browser code.
- **Rate limiting:** still deferred. Authentication bounds *who* can write, not
  *how much*; abuse controls come later.
- **Legacy `/v1/traces`:** remains open and unchanged so the existing demo/SDK
  keep working. It stays a temporary unsecured compatibility route until the
  SDK and frontend move to the authenticated v2 path; no removal date is set.

### Effect on the quickstart and future SDKs

The OTel quickstart now reads `HELIOS_API_KEY` and sends
`Authorization: Bearer`; it no longer sends a project slug and never prints the
key. Future first-party SDKs and auto-instrumentation should follow the same
contract: accept a project key via config/env, send it as a bearer token, and
let the server derive the project. The temporary project headers are gone from
the canonical path.

## Consequences

- Managing keys requires the admin CLI (`python -m app.cli.api_keys`); there is
  no self-service or browser flow yet.
- Every canonical request does one extra small DB write (`last_used_at`) in an
  isolated transaction.
- Legacy and canonical paths now differ in security posture; this is intended
  and documented, not an oversight.
