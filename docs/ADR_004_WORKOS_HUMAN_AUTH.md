# ADR 004: WorkOS AuthKit Human Authentication and Organization Scoping

Status: Accepted · Branch: `helios-v2-otel-foundation` · Builds on
[ADR 002](ADR_002_PROJECT_API_KEYS.md) (project API keys).

## Context

Machine authentication (project API keys) shipped in ADR 002, but humans had no
way to sign in: `/app/*` was public and no backend route knew who a user was.
Helios needs hosted human authentication and organization-scoped access without
building password infrastructure.

## Decision

### WorkOS AuthKit authenticates humans; Helios never stores passwords

WorkOS AuthKit provides hosted sign-in (email+password, SSO-ready later),
session management, JWTs, and organizations. Helios implements no first-party
passwords, password hashes, refresh-token storage, or session tables — WorkOS
is the identity, membership, and session source of truth. This trades a vendor
dependency for drastically less security-critical surface area.

**Selected package:** `@workos/authkit-tanstack-react-start` **0.11.0**
(official; verified against npm metadata 2026-06). Peer-requires
`@tanstack/react-start >=1.168.25`, which forced an in-range TanStack bump
(react-start 1.168.28, react-router 1.170.18, router-plugin 1.168.20). The
package is pre-1.0: expect API movement on upgrade.

### Credential boundary: human JWTs vs project API keys

| | Humans (browser) | Machines (SDK/services) |
|---|---|---|
| Credential | WorkOS access token (JWT) | `hel_proj_*` project API key |
| Routes | `/v2/user/*` | `/v1/otlp/traces`, `/v2/traces*` |
| Scope source | `org_id` claim | key's project |

The browser never receives or uses a project API key; user JWTs cannot ingest
OTLP; project keys cannot call `/v2/user/*`. Neither dependency calls the other.

### TanStack Start owns the session; FastAPI verifies tokens

- **TanStack Start (server)** runs the AuthKit middleware, session cookies, and
  the auth routes (`/api/auth/sign-in|sign-up|callback|sign-out`). Server-only
  env: `WORKOS_CLIENT_ID`, `WORKOS_API_KEY`, `WORKOS_REDIRECT_URI`,
  `WORKOS_COOKIE_PASSWORD` — never `VITE_*`, never imported into browser code.
  A custom `startInstance` disables the framework's automatic CSRF protection,
  so `createCsrfMiddleware` is re-added explicitly (order: CSRF → Helios error
  boundary → AuthKit). The AuthKit middleware attaches only when
  `WORKOS_CLIENT_ID` is set, so builds/CI/the public demo work without
  credentials and auth routes fail with a clear error instead of breaking every
  request.
- **FastAPI** verifies the WorkOS **access token** independently: RS256
  signature via the WorkOS JWKS, issuer, exp/iat, and required `sub`/`sid`
  (+`org_id` for org-scoped routes). WorkOS access tokens carry no `aud` claim,
  so audience verification is disabled (documented; the issuer embeds the
  client ID). Verification needs only `WORKOS_CLIENT_ID` (issuer/JWKS URL are
  derived, or overridable via `WORKOS_ISSUER`/`WORKOS_JWKS_URL`) — the WorkOS
  server API key is *not* required to validate tokens.

### Why the browser calls FastAPI directly with the bearer token (no BFF)

A backend-for-frontend proxy would add a second server hop, session-to-token
exchange, and more state for no security gain at this stage: the access token
is short-lived, obtained fresh per call via the SDK (`getAccessToken()`), never
persisted to local/sessionStorage, and FastAPI verifies it cryptographically.
A BFF is deferred until requirements (token hiding, response shaping,
rate-limit placement) actually demand one.

### JWKS caching and failure behavior

Bounded in-memory cache (TTL `WORKOS_JWKS_CACHE_TTL`, default 3600 s) so JWKS
is not fetched per request; refresh on expiry; exactly one forced refresh when
an unknown `kid` appears (key rotation); explicit HTTP timeout
(`WORKOS_JWKS_TIMEOUT`, default 5 s); any fetch failure **fails closed** (401).
JWTs, Authorization headers, and JWKS responses are never logged.

### Organization-wide project access (first version)

A verified `org_id` claim proves active organization membership; **all members
of a linked organization may read all of its projects**. `role` and
`permissions` claims are carried in the auth context for future authorization
but not yet enforced per-project. Explicit per-project membership is deferred:
it needs product design (invites, roles, UI) that would bloat this checkpoint,
and WorkOS org membership already provides a real tenancy boundary.

### Local identity mapping (JIT users, admin-linked orgs)

- `users`: upserted/touched automatically on first verified request (JIT), in
  an isolated committed session; stores only WorkOS `sub` + timestamps
  (email/display fields exist but are unset until a trustworthy source is wired).
- `organizations`: **never** auto-created from tokens. An admin links a WorkOS
  org via `python -m app.cli.organizations create`; an unknown `org_id` gets a
  stable 403 onboarding response. This prevents arbitrary external org IDs from
  implicitly owning projects. No local membership table (WorkOS is membership
  truth; documented choice).
- `projects.organization_id` (nullable FK): existing projects keep their UUIDs,
  API keys, and traces; assignment is explicit via
  `python -m app.cli.organizations assign-project`. One project belongs to at
  most one organization. Global project-slug uniqueness is retained.

### Development and test behavior

Tests never call WorkOS: a locally generated RSA key signs WorkOS-shaped JWTs
and a fetcher-injected JWKS client serves the matching JWKS
(`backend/tests/workos_helpers.py`). CI needs no WorkOS credentials. Local
verification uses the same path; hosted login requires a real WorkOS dev
environment (documented, manual).

### Vendor lock-in and migration boundary

WorkOS-specific surface is deliberately narrow: the frontend package, the
`workos_*` columns (`users.workos_user_id`, `organizations.workos_org_id`), and
`app/security/workos_auth.py`. Replacing WorkOS later means swapping the
frontend auth package, re-pointing the verifier at another OIDC issuer/JWKS,
and remapping the two external-ID columns — project/trace ownership and the
API-key system are identity-provider-agnostic.

## Consequences

- `/app/*` now requires WorkOS configuration at runtime; without it those
  routes fail with a clear configuration error (public marketing routes and
  the machine API are unaffected).
- Trace list/detail and the project dashboard read `/v2/user/projects/*` with
  WorkOS JWTs (Checkpoints 6–7). RAG, evaluations, prompts, datasets,
  experiments, and settings still use legacy `/v1` or static UI and may retain
  demo fallback until a later migration.
- An organization switcher is deferred: the session exposes only the active
  organization, and enumerating a user's organizations requires WorkOS API
  calls that belong with real org-management UX.
