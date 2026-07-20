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
- [x] Alembic head remains `004_human_identity`

## Still requires manual staging verification

- [ ] Create Vercel staging project and fixed hostname
- [ ] Create Render staging web service + PostgreSQL
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
