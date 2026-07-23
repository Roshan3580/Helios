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
- [x] Alembic head remains `004_human_identity` (Checkpoint 24 adds no migration)

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

A hosted Vercel frontend and a hosted Render backend + PostgreSQL exist and
**currently serve demo/sample data** (owner-confirmed, Checkpoint 17). The
items below that concern *creating* the hosted infrastructure are therefore
done; the items that concern *validating real authenticated behavior on
staging* (WorkOS login, smoke tests, real-tenant browser flows) remain
**pending** — the deployment has not yet been exercised with real WorkOS
sign-in or real multi-tenant data. Do not treat hosted deployment as
production-ready until those are verified.

## Still requires manual staging verification

- [x] Create Vercel staging project and fixed hostname (hosted frontend live)
- [x] Create Render staging web service + PostgreSQL (hosted backend live, demo data)
- [ ] Apply/configure WorkOS **staging** redirect/sign-in/sign-out URIs
- [ ] Set real staging secrets in platform dashboards (never in git)
- [ ] Run migrations via Render pre-deploy on a real database
- [ ] Hosted `/health/live` and `/health/ready`
- [ ] Hosted CORS between fixed frontend and API origins
- [ ] HTTPS cookie / SameSite behavior with AuthKit
- [ ] Real WorkOS staging login, org switching, sign-out
- [ ] `scripts/smoke-staging.sh` against real staging URLs
- [ ] Browser project/key/OTLP/Dashboard/Traces/Insights on staging
- [ ] Vercel/Render runtime logs and cold-start behavior
- [ ] Optional: enable narrative + real OpenAI only after explicit review
- [ ] Broader browser/visual review

## Still prohibited / not done

- [ ] Production deploy
- [ ] Production WorkOS environment
- [ ] Automatic production promotion
- [ ] Enabling E2E seam outside local/CI harness

Do not mark manual staging or production items complete from CI alone.

See [STAGING_DEPLOYMENT.md](./STAGING_DEPLOYMENT.md).
