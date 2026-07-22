# Browser E2E release gate

## Purpose

Checkpoint 13 adds a Chromium Playwright suite that exercises Helios’s canonical
authenticated journey end-to-end: zero-project onboarding, self-serve project
creation, one-time project API-key reveal, OTLP ingestion, traces, deterministic
analysis, project insights, revocation, and organization isolation.

This is a **release gate**, not a substitute for staging login against real WorkOS.

## Playwright version

Pinned in `package.json` as `@playwright/test@1.57.0` (Chromium only).

## Authentication seam (Option B)

Production AuthKit / WorkOS hosted login is **not** used in CI.

Instead, `scripts/run-e2e.sh` starts:

1. Isolated Postgres (`docker-compose.test.yml`)
2. A loopback JWKS HTTP server with an ephemeral RSA key
3. FastAPI configured with that issuer/JWKS, narrative disabled, no OpenAI key
4. Vite with `VITE_HELIOS_E2E_TEST_MODE=true` and a **server-only** runtime JWT
   (`HELIOS_E2E_ACCESS_TOKEN`) minted for a pre-linked test organization

The frontend `/app` `beforeLoad` skips AuthKit when
`VITE_HELIOS_E2E_TEST_MODE=true` (boolean only — never a token). The access
token is served only from `/api/e2e/session`, which requires
`evaluateE2EServerAccess` to pass:

- `NODE_ENV !== production`
- `HELIOS_E2E_TEST_MODE=true`
- runtime access token present
- JWKS/issuer are loopback

Tokens are never `VITE_*` build-time values and are never committed. Backend
verification is the real WorkOS JWT path against the loopback JWKS.

## Local prerequisites

- Docker (for `docker-compose.test.yml`)
- Bun
- Python 3.12 backend venv at `backend/.venv` with `requirements-dev.txt`
- Playwright Chromium: `bunx playwright install chromium --with-deps`

## Commands

```bash
bun run test:e2e          # harness + headless Chromium
bun run test:e2e:headed   # headed spot-check
bun run test:e2e:debug    # Playwright debug
bun run test:e2e:report   # open last HTML report
```

CI runs the same harness via the `Browser E2E (Chromium)` job
(`bash scripts/run-e2e.sh`, one worker, retries=1).

## Secret handling

- Plaintext project keys exist only in test memory / a 0600 temp file for OTLP.
- Screenshots: failure-only; video off; traces on first retry.
- Tests assert the key is absent from URL, localStorage, sessionStorage, and cookies.
- Failure artifacts may still be sensitive — treat uploads as secret-bearing.

## Flows covered

- Zero-project Dashboard / Traces / Insights → Getting started
- Project create + selection persistence (`helios.selectedProjectId` only)
- API key create / one-time reveal / copy / dismiss
- OTLP ingest + onboarding “Check for traces”
- Trace detail + deterministic analysis + narrative-disabled copy
- Project insights (seeded via `/v2/e2e/seed-insights` under E2E mode)
- Key revocation + failed machine auth
- Cross-org isolation (separate JWTs / request contexts)
- Narrow viewport smoke

## Flows not covered

- Real WorkOS hosted login / callbacks / org switcher UI
- Safari / WebKit / Firefox
- Production deploy, HTTPS cookies, CORS to production hosts
- Real OpenAI narrative completion
- Legacy/demo analytics pages as canonical product
- Full accessibility conformance or visual baselines

## Troubleshooting

- Backend log: harness temp dir `backend.log` (printed path under `/tmp/helios-e2e.*`)
- Frontend log: `frontend.log` in the same temp dir
- Ensure port 5434 is free for test Postgres
- Ensure `backend/.venv` exists before running the harness

## Expected runtime

Roughly 3–8 minutes locally depending on cold Docker/Playwright downloads;
CI budget is a 30-minute job timeout.
