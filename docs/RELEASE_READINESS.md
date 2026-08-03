# Release readiness

Helios v2 separates **automatically verified** gates from **manual staging**
and **production** work.

## Verified automatically

- [x] Frontend typecheck / lint / production build
- [x] Backend PostgreSQL suite
- [x] Python SDK suite
- [x] TypeScript SDK suite (Checkpoint 16): unit tests, dual-build package
      verification (pack allowlist + ESM/CJS/TS consumers), real local
      backend OTLP integration, artifact secret scan; package **not**
      published to npm
- [x] Chromium browser release gate (Checkpoint 13)
- [x] Deployment contract checks (Checkpoint 14): staging config validation,
      CORS policy, `/health/live` + `/health/ready`, migration-check CLI,
      `render.yaml` placeholders, `.env.staging.example`, browser bundle secret scan
- [x] Narrative disabled by default; no real OpenAI call in CI
- [x] E2E seam forbidden under staging-shaped configuration
- [x] Legacy/demo API surface (Checkpoint 18): mounted only under explicit
      `HELIOS_DEMO_MODE=true`; forbidden under staging-shaped configuration
      (same mechanism as the E2E seam); canonical OTLP and `/v2/*` unaffected
- [x] Self-serve onboarding (Checkpoint 24): a verified WorkOS organization is
      mapped to a local Helios organization automatically and tenant-safely on
      first sign-in (no admin CLI/SQL). Organization identity comes only from
      the verified token; concurrent first requests converge on one row;
      cross-org resources remain a safe 404
- [x] Free invited-beta configuration contract (Checkpoint 24):
      `scripts/check-free-beta-config.sh` (run in the Deployment contract job)
      validates `.env.beta.example` (demo/e2e/narrative false, exact CORS, no
      wildcard, server-only WorkOS secrets, placeholder DB URL) and that
      `render.yaml` remains the paid staging contract
- [x] Alembic head remains `004_human_identity` (Checkpoints 24–27 add no migration)
- [x] AuthKit access-token readiness (Checkpoint 27): the client distinguishes
      auth loading, token initializing, token ready, token acquisition failed,
      and backend 401. Token initialization is **never** classified as session
      expiry, no authenticated request is issued without a token, and N
      concurrently mounted hooks share exactly one bounded token acquisition.
      Covered by `src/lib/auth/token-readiness.test.ts` and the
      `e2e/04-token-readiness.spec.ts` browser gate (delayed token
      initialization must not render an expiry panel)
- [x] WorkOS multi-application issuer contract (Checkpoint 30): standard,
      multi-application, and explicit modes are mutually exclusive; the
      multi-application issuer comes only from backend-only
      `WORKOS_ISSUER_CLIENT_ID`, while JWT `client_id` and JWKS remain tied to
      `WORKOS_CLIENT_ID`

## Invited free beta (Checkpoint 24)

The real product can be run for **invited testers** on zero-cost infrastructure
(existing Vercel `helios-staging` project + WorkOS Staging + a new Render **Free**
`helios-api-beta` backend + one external free PostgreSQL). This is **not** an
SLA-backed production service. Authenticated pages surface a bounded "Helios
Beta is waking up" notice on Render Free cold starts and **never** fall back to
demo data. See `docs/FREE_BETA_DEPLOYMENT.md` and `.env.beta.example`. Hosting
the beta (creating the Render service + external DB, wiring Vercel/WorkOS,
running the real OTLP journey) is manual and out of scope for this source-only
checkpoint.

## Hosted deployment status

A production-capable hosted beta is operational at the confirmed Vercel
frontend and Render backend. The complete real journey has verified WorkOS
authentication, organization authorization and bootstrap, project and key
creation, authenticated OTLP ingestion, trace inspection, deterministic
analysis, dashboard aggregation, project insights, key revocation, revoked-key
rejection with 401, and no post-revocation trace write. This is an invited beta,
not a generally available or SLA-backed production service. Repeat the bounded
[hosted beta smoke test](./HOSTED_BETA_SMOKE_TEST.md) for a release candidate.

## Verified hosted beta journey

- [x] Create Vercel staging project and fixed hostname (hosted frontend live)
- [x] Create Render web service + PostgreSQL (hosted beta backend live)
- [x] Apply WorkOS staging redirect, sign-in, and sign-out configuration
- [x] Configure hosted secrets through platform dashboards
- [x] Apply migrations to the hosted beta database
- [x] Hosted `/health/ready`
- [x] Hosted CORS between fixed frontend and API origins
- [x] HTTPS AuthKit sign-in and session behavior
- [x] Real WorkOS login and organization-scoped authorization
- [x] Organization and identity bootstrap
- [x] Browser project/key/OTLP/Dashboard/Traces/Analysis/Insights journey
- [x] Project API-key revocation, 401 rejection, and no rejected trace write
- [x] Render cold-start behavior documented as a bounded operational condition
- [ ] Optional: enable narrative + real OpenAI only after explicit review
- [ ] Broader browser/visual review

## Deferred release work

- [ ] Public Python SDK publication
- [ ] Public TypeScript SDK publication
- [ ] Self-serve workspace onboarding
- [ ] Usage limits and retention
- [ ] Operational recovery hardening
- [ ] Separate demo database restoration
- [ ] Full em-dash removal across production and demo user-facing copy

## Still prohibited / not done

- [ ] Production deploy
- [ ] Production WorkOS environment
- [ ] Automatic production promotion
- [ ] Enabling E2E seam outside local/CI harness

Do not infer future hosted verification from CI alone. Follow the operator
runbook and record only safe pass or fail evidence.

See [STAGING_DEPLOYMENT.md](./STAGING_DEPLOYMENT.md) and
[HOSTED_BETA_SMOKE_TEST.md](./HOSTED_BETA_SMOKE_TEST.md).
