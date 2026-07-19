# Release readiness

Helios v2 Checkpoint 13 separates **automatically verified** gates from
**manual staging** work that still requires humans and non-production hosted
services.

## Verified automatically

- [x] Frontend typecheck / lint / production build
- [x] Backend PostgreSQL suite (includes project create, API keys, OTLP, analysis, insights, auth)
- [x] Python SDK suite
- [x] Browser onboarding (zero-project → create project)
- [x] One-time project API key reveal + copy + dismiss
- [x] OTLP ingestion with project key
- [x] Machine reads with scoped keys
- [x] Key revocation blocks machine auth
- [x] Dashboard against live telemetry (no demo fallback in E2E)
- [x] Traces list/detail
- [x] Deterministic single-trace analysis
- [x] Project insights (deterministic window analysis)
- [x] Organization isolation (cross-org 404 / separate JWTs)
- [x] No real OpenAI / provider call in CI or E2E harness
- [x] Alembic head remains `004_human_identity` (no Checkpoint 13 migration)

## Still requires manual staging verification

- [ ] Real WorkOS staging login
- [ ] Callback and sign-out redirect URIs
- [ ] Organization switching in AuthKit UI
- [ ] Hosted HTTPS cookies
- [ ] Real deployment environment variables
- [ ] Vercel server/runtime behavior
- [ ] Render/PostgreSQL connectivity
- [ ] Production CORS
- [ ] Production OTLP endpoint
- [ ] Real OpenAI call if narrative will be enabled
- [ ] Provider retention configuration
- [ ] Responsive visual review beyond smoke
- [ ] Supported browser review (Safari/Firefox)

Do not mark manual items complete from CI alone.
