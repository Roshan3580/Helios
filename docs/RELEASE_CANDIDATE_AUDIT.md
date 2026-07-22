# Release-Candidate Audit (Checkpoint 17)

Audit of branch `helios-v2-otel-foundation` at commit `370d193` (before this
checkpoint's commit). Goal: decide whether the branch is technically ready to
become a release candidate toward `main`, apply only justified release-blocking
fixes, and record everything else.

Method: seven parallel read-only audits (auth, data isolation, privacy +
narrative, OTLP + database + reliability, frontend + product boundary, SDKs, CI
+ dependencies + documentation), each tracing actual code and tests rather than
prior checkpoint reports. No secret values appear in this document.

## Scope audited

Backend API; human authentication (WorkOS JWT); machine authentication
(`hel_proj_*`); project onboarding; API-key lifecycle; OTLP ingestion;
dashboard; trace list/detail; single-trace analysis; project insights; optional
narrative; Python SDK; TypeScript SDK; browser release gate; deployment
contract; CI; documentation; legacy/demo boundaries; database schema, migrations
and indexes; dependency posture.

## Executive result

The **canonical v2 platform is well-built and correctly isolated.** Every v2
subsystem (dashboard, trace list/detail, single-trace analysis, project
insights, OTLP ingest, API-key list/revoke) binds `project_id` and is org-gated,
each with a dedicated cross-project/cross-org regression test. Human and machine
auth are defensive (RS256-only JWT with `alg`-confusion resistance and
fail-closed JWKS; constant-time key-hash compare; scope enforcement; immediate
revocation; credential families never interchangeable). Privacy and narrative
handling are strong: no generated secret leaks into any tracked file, browser
bundle, or SDK artifact; narrative is disabled by default behind dual opt-in,
cannot invent evidence, and its provider bundles exclude content, identity, and
credentials.

The material release-relevant issues were **not in the v2 path**. They were: (1)
the legacy unauthenticated `/v1` surface, (2) a product-boundary problem where
demo pages were indistinguishable from real telemetry, and (3) several
documentation contradictions. (2) and (3) were fixed in Checkpoint 17; (1) is
fixed in Checkpoint 18 — legacy/demo routers are now mounted only under
explicit `HELIOS_DEMO_MODE=true`, which is itself forbidden in staging/
production by startup validation. The hosted demo (which intentionally serves
demo-only data) continues to run by explicitly setting `HELIOS_DEMO_MODE=true`
in its own environment classification; this is unaffected by the fix.

## Findings

| ID | Severity | Subsystem | Finding | Resolution |
| -- | -------- | --------- | ------- | ---------- |
| L1 | HIGH → fixed (Checkpoint 18) | Legacy API / isolation | Legacy `/v1` routers were mounted unauthenticated over the shared `projects` table regardless of configuration: `GET /v1/projects` enumerated every organization's projects; `/v1/traces` allowed unauthenticated read/write of the legacy trace store; `/v1/dashboard/summary`,`/v1/rag`,`/v1/evaluations`,`/v1/prompts`,`/v1/datasets` were unauthenticated legacy reads; `POST /v1/demo/seed` was gated only by an in-handler check (`helios_demo_mode`, defaulted `True`, not checked by deployment validation). | **Fixed.** `app.main.create_app()` now mounts the eight legacy/demo routers only when `HELIOS_DEMO_MODE` is explicitly `true` — never per-endpoint authentication, the security boundary is not mounting them at all. The default changed to `false`. `deployment_validation.validate_settings` now rejects `HELIOS_DEMO_MODE=true` in staging/production (new `demo_mode_forbidden` issue), enforced at ASGI startup (`app.main.lifespan`) and by `python -m app.cli.deployment_check --config-only` — failing before any traffic is served, not first at `/health/ready`. Canonical `POST /v1/otlp/traces` and all `/v2/*` routes are mounted unconditionally and are unaffected. See `backend/tests/test_legacy_demo_gating.py` for route-mounting/OpenAPI/canonical-preservation regression coverage. |
| P1 | HIGH → fixed | Frontend product boundary | Five legacy/demo surfaces (RAG Analytics, Prompts, Evaluations, Datasets, Experiments) appeared in primary nav with no label; RAG Analytics sat in the `Observe` group beside real telemetry; demo data rendered with no on-screen notice in the default (demo-on) build; the app shell showed a fabricated `ingest 1.2k/s` badge on every canonical page. | **Fixed.** Demo surfaces moved out of `Observe`, labeled with a visible `Demo` badge; `DataSourceNotice` now renders for `demo` (not only `fallback`); Experiments gained a top-of-page demo notice; the fabricated ingest badge was removed. E2E asserts the badge is gone and the legacy nav is labeled. |
| D1 | HIGH → fixed | Documentation | README/RELEASE_READINESS/render.yaml disagreed on whether the backend is deployed. | **Fixed after owner confirmation** that the Render backend + Postgres are hosted and currently serve demo data. README keeps the deployment claim (now pointing at the canonical OTLP path and both SDKs, and noting the hosted backend showcases demo data); RELEASE_READINESS records hosted infrastructure as done while real WorkOS staging login / real-tenant validation remain pending. |
| D2 | MEDIUM → fixed | Documentation | `ARCHITECTURE.md` "Design tradeoffs" / "Future architecture" claimed auth, OpenTelemetry, and the TypeScript SDK were unbuilt, and listed a "browser" TS SDK (contradicting the rest of the doc and `TYPESCRIPT_SDK.md` which marks browser unsupported). | **Fixed.** Sections rewritten to reflect shipped auth (WorkOS + project keys), shipped OTLP path, shipped Python + Node SDKs (Node-only, browser unsupported). |
| D3 | MEDIUM → fixed | Documentation | `sdk/python/README.md` stated the TypeScript SDK is "future work and not yet supported". | **Fixed.** Now points to the shipped `@helios-ai/sdk` and `docs/TYPESCRIPT_SDK.md`. |
| D4 | LOW → fixed | Documentation | README "Future improvements" listed the shipped TypeScript SDK and shipped human auth as future. | **Fixed.** List updated to genuine remaining work (rate limiting, gate `/v1`, migrate legacy pages, RBAC, publish TS SDK). |
| SDK1 | HIGH → fixed | Python SDK | `pyproject.toml` declared no license, authors, urls, keywords, or classifiers — an accidental `twine upload` would have no publication guard. | **Fixed (metadata only, no license selected).** Added authors/keywords/urls and classifiers including `Private :: Do Not Upload` (PyPI rejects upload) + `License :: Other/Proprietary License`, mirroring the TS SDK's intentional unpublished posture. |
| CI1 | MEDIUM → fixed | CI | No `permissions:` block; `GITHUB_TOKEN` inherited the repo default (potentially read/write-all). | **Fixed.** Added top-level `permissions: contents: read`. No job publishes/deploys/writes, so artifact upload is unaffected. |
| CI2 | MEDIUM → fixed | CI | `frontend`, `backend-tests`, `sdk-tests` had no `timeout-minutes` (6h default). | **Fixed.** Added 15/20/15-minute timeouts; all six jobs are now bounded. |
| ISO1 | MEDIUM | Data isolation (v2, latent) | v2 read/analysis services re-resolve the project by globally-unique `slug` (`otel_trace_service.get_project_by_slug`) instead of the already-authorized `project_id`. Safe today because `projects.slug` is globally unique; becomes a cross-org risk only if per-org slug uniqueness is ever introduced. | **Documented.** Not exploitable now; fixing touches multiple service signatures. Thread `project_id` through when per-org slugs are introduced. |
| OTLP1 | MEDIUM | OTLP ingestion | The 4 MiB body cap is enforced only after `await request.body()` fully buffers the payload; no `Content-Length` pre-check or ASGI body-limit middleware. A single oversized request can pressure the sole worker before rejection. | **Documented.** Hosting/edge limits partially mitigate; a streaming/Content-Length guard is the follow-up. |
| OTLP2 | MEDIUM | OTLP ingestion | `environment` and other string fields are not length-validated before insert, so an over-length value raises a DB error surfaced as a generic 500 instead of a 400. No corruption (transaction rolls back). | **Documented.** Add length validation → 400 as a follow-up. |
| REL1 | MEDIUM | Legacy reliability | Legacy `/v1/traces` and `/v1/demo` return `detail=str(exc)` (can surface DB internals); legacy list endpoints (`/v1/dashboard/summary`, `/v1/rag`, project/org lists) are unbounded full-table loads. | **Documented** (subsumed by L1 — these are on the unauthenticated legacy surface to be gated before real tenants). Canonical v2 paths sanitize errors and bound all lists. |
| SDK2 | MEDIUM | Python SDK / parity | Python SDK does not enforce HTTPS for non-loopback endpoints, so a misconfigured remote endpoint could transmit the Bearer key over plaintext HTTP (the TS SDK blocks this). | **Documented.** Port the TS loopback/HTTPS guard (with an explicit insecure-opt-in) as a follow-up; behavior change deferred to avoid rejecting currently-valid configs without a dedicated test pass. |
| REL2 | LOW | Reliability | `/health/ready` detects a never-migrated DB but does not compare the stored Alembic revision to head (a behind-head DB reports ready). v2 trace list `ORDER BY start_time` has no tiebreaker. | **Documented.** |
| SEC1 | LOW | CI / secrets | Third-party actions pinned to floating major tags (not SHAs); Playwright failure artifacts (7-day retention) could capture an ephemeral test key; Python deps are unpinned (no lockfile). | **Documented.** |
| SDK3 | LOW | TypeScript SDK | `dist/**` ships `*.js.map`/`*.d.ts.map` without `src`, so consumer go-to-source is broken (no source leak — `inlineSources` off). | **Documented.** |
| N1 | LOW | Narrative | `store=false` on the OpenAI adapter is verified in source but not asserted by a test (tests use fake providers); the unsupported-claim regex is a heuristic (evidence-ID binding remains the hard control). | **Documented.** |
| DEP1 | LOW | Dependencies | `bun audit` reports 4 advisories (babel, brace-expansion, esbuild, js-yaml) — all in dev/build-time trees, none reachable by the deployed app. `npm audit --omit=dev` on the TS SDK = 0; `pip check` clean. | **Documented, no change.** Not exploitable in product usage. |
| AUTH-CLEAN | NOT AN ISSUE | v2 auth | WorkOS JWT required everywhere; RS256-only; unlinked org → 403; cross-org → 404; project keys rejected on human routes and vice versa; body/query cannot override org/project; E2E seam gated + rejected in staging/prod. Machine keys: constant-time hash, scopes enforced, immediate revocation, no cross-project existence leak. | Verified clean, with tests. |
| PRIV-CLEAN | NOT AN ISSUE | Privacy/secrets | No generated secret in any tracked file, browser bundle, SDK artifact, or Playwright output; one-time key held in memory only; SDK content-capture off by default; errors redact keys. | Verified clean, with tests. |
| DB-CLEAN | NOT AN ISSUE | Database | Single Alembic head `004_human_identity`; ORM fully covered by migrations; no startup `create_all`; Render `preDeployCommand: alembic upgrade head` with `--workers 1`; all required indexes present; test-DB guardrails reject test DBs in staging/prod. | Verified clean. |

## Fixed in Checkpoint 17

Code / config:

- `src/components/helios/app-shell.tsx` — moved legacy demo pages out of the
  `Observe` group, added a visible `Demo` badge to legacy nav entries, removed
  the fabricated `ingest 1.2k/s` status badge (and its now-unused import).
- `src/components/helios/data-source-notice.tsx` — render a visible notice for
  `demo` data (previously only `fallback`); `api` (real v2 data) renders nothing.
- `src/routes/app.experiments.tsx` — added a top-of-page demo notice.
- `e2e/01-canonical-journey.spec.ts` — assert the fabricated ingest badge is
  absent on the dashboard and that the RAG Analytics nav entry is labeled `Demo`
  (assertions added inside the existing test; suite count unchanged at 12).
- `.github/workflows/ci.yml` — added `permissions: contents: read`; added
  `timeout-minutes` to `frontend`, `backend-tests`, `sdk-tests` (all six jobs
  now bounded).
- `sdk/python/pyproject.toml` — added authors, keywords, urls, and classifiers
  (`Private :: Do Not Upload`, `License :: Other/Proprietary License`, …) to
  guard against accidental publication and complete package metadata, without
  selecting a real license.

Documentation:

- `README.md` — deployment sentence points to the canonical OTLP path and both
  SDKs and notes the hosted backend showcases demo data; "Future improvements"
  updated to genuine remaining work.
- `docs/ARCHITECTURE.md` — "Design tradeoffs" / "Future architecture" rewritten
  to reflect shipped auth, OTLP, and SDKs (Node-only; browser unsupported).
- `docs/RELEASE_READINESS.md` — added a "Hosted deployment status" note and
  checked the hosted-infrastructure items; validation items remain unchecked.
- `sdk/python/README.md` — corrected the claim that the TypeScript SDK does not
  exist.
- `docs/RELEASE_CANDIDATE_AUDIT.md` — this document.

## Fixed in Checkpoint 18

Code / config:

- `backend/app/main.py` — introduced `create_app()` (factory instead of a
  module-level singleton with unconditional `include_router` calls); legacy/
  demo routers (`projects`, `traces`, `dashboard`, `rag`, `evaluations`,
  `prompts`, `datasets`, `demo`) are mounted only when `settings.helios_demo_mode`
  is true. Canonical `otlp`, `traces_v2`, `user_v2`, and `health` are always
  mounted, independent of the flag.
- `backend/app/config.py` — `helios_demo_mode` default changed `True` → `False`.
- `backend/app/deployment_validation.py` — `validate_settings` gained a
  `helios_demo_mode` parameter; staging/production with it `true` now produces
  a `demo_mode_forbidden` issue, enforced at ASGI startup (`app.main.lifespan`)
  and by `python -m app.cli.deployment_check --config-only` — the same
  mechanism already used for `HELIOS_E2E_TEST_MODE`.
- `backend/app/cli/deployment_check.py` — passes `helios_demo_mode` through to
  `validate_settings`.
- `backend/tests/test_legacy_demo_gating.py` (new) — route-mounting, OpenAPI
  presence/absence, canonical-OTLP-preservation, canonical-`/v2`-preservation,
  and unsafe-environment-startup regression coverage.
- `backend/tests/conftest.py` — the shared `client` fixture's app now resolves
  `HELIOS_DEMO_MODE=false` deterministically (forced before import, matching
  the existing pattern for `DATABASE_URL`/`HELIOS_ENVIRONMENT`); added
  `legacy_demo_client` for the few tests that exercise the legacy surface
  directly.
- `scripts/check-deployment-contract.sh` — added an explicit
  `HELIOS_DEMO_MODE=false` to the staging-shaped config check and a regression
  guard asserting `HELIOS_DEMO_MODE=true` fails that same check.
- `.env.example`, `.env.staging.example` — comments clarify the flag's effect
  and its staging/production prohibition.

Documentation: this document (L1 marked fixed), `README.md`,
`docs/ARCHITECTURE.md`, `docs/RELEASE_READINESS.md`,
`docs/DEPLOYMENT_ENVIRONMENT_MATRIX.md`, `docs/STAGING_DEPLOYMENT.md`.

CI: `.github/workflows/ci.yml` already had `timeout-minutes` on all six jobs
(Frontend 15, Backend tests 20, Python SDK tests 15, TypeScript SDK 25,
Browser E2E 30, Deployment contract 20) prior to this checkpoint — a prior
verification report's claim that three jobs lacked timeouts was itself
inaccurate; no CI change was needed or made.

## Open release blockers

None that block opening a release-candidate PR of the v2 platform.

## Open before real multi-tenant / production use (must-fix)

1. **Validate real WorkOS staging login and real-tenant browser flows** on the
   hosted deployment (currently demo-data only). This is now the primary
   remaining item; finding L1 (legacy `/v1` surface) is closed as of
   Checkpoint 18.

## Accepted limitations

- Hosted **staging validation not completed**; real WorkOS staging login not
  tested (hosted backend serves demo data only).
- **Organization-wide access** is the model; no per-project RBAC.
- **Global project-slug uniqueness** (documented; v2 relies on it today).
- **Narrative disabled by default**; requires dual opt-in; no real OpenAI call.
- **TypeScript SDK not published** to npm and **`UNLICENSED`** (publication
  blocker); Python SDK likewise repository-artifact only, marked
  `Private :: Do Not Upload`.
- **Browser telemetry unsupported** (server SDKs only).
- **Legacy/demo pages retained** but labeled `Demo`, moved out of the
  telemetry-focused nav group, and now served only when the backend
  explicitly opts into `HELIOS_DEMO_MODE=true`.
- **No real OpenAI / external provider call** in tests or CI.
- **Chromium-only** automated browser testing.

## Merge recommendation

**READY FOR RELEASE-CANDIDATE PR.**

The canonical v2 platform is correctly isolated, defensively authenticated,
privacy-safe, transactionally sound, and covered by cross-project/cross-org
regression tests; documentation contradictions and the misleading product
boundary are fixed; CI is hardened; the legacy `/v1` surface (finding L1) is
now gated behind explicit demo mode and forbidden in staging/production. The
branch can open a release-candidate PR toward `main`.

It is **not** "ready to merge" for real production/multi-tenant use until
hosted staging and real WorkOS login/real-tenant browser flows are validated.
Consistent with the project's own readiness gate, production release is not
recommended without that validation.

## Fixed in Checkpoint 22

Checkpoint 21 (H1/H3) updated `render.yaml`'s `preDeployCommand` to
`python -m app.cli.deployment_check --config-only && alembic upgrade head`,
but `scripts/check-deployment-contract.sh`'s `render.yaml` structural check
(both the PyYAML and no-PyYAML code paths) still asserted the old exact
value `preDeployCommand: alembic upgrade head`. This made the deployment
contract job fail in CI regardless of PyYAML availability — reproduced
locally in an isolated interpreter with no PyYAML and, separately, in the
existing backend `.venv` where PyYAML *is* present (transitively, via
`uvicorn[standard]`), confirming the defect was in the stale assertion, not
environment drift. Checkpoint 21's local report of "Deployment contract: OK"
did not actually exercise this path correctly and was inaccurate.

Fixed by consolidating both parsing paths onto one shared ordering check
(`check_ordering`) that verifies, from either PyYAML-parsed or
regex-extracted `preDeployCommand` text: the config-only command precedes
`alembic upgrade head`, they are joined with fail-fast `&&` (not `;`), and
no `downgrade` command is present. The script now also runs a self-contained
fixture pass (valid case + five deliberately invalid cases: reversed order,
missing config command, missing migration command, `;`-joined, downgrade
present) before checking the real `render.yaml`, so both code paths are
provably fail-closed rather than merely passing on today's file.

Verified: `bash scripts/check-deployment-contract.sh` passes end-to-end
locally (PyYAML present); the same check block re-run in an isolated
venv without PyYAML also passes, printing
`render.yaml structural OK (stdlib fallback; PyYAML unavailable)`; a
deliberately reversed-order `render.yaml` was injected and confirmed to
fail with `config validation must run before migration`, then reverted.

Also reconciled the Checkpoint 21 backend test-count discrepancy (report
said 463; a prior GitHub Actions summary quoted 460). The 460 figure came
from misreading the *previous* commit's (`140a2fb`) CI run instead of the
run for the H1/H3 commit itself. The H1/H3 commit added exactly 3 new test
functions (`test_unknown_environment_prod_is_fatal`,
`test_unknown_environment_with_demo_mode_fails_closed`,
`test_unknown_environment_production_variant_fails`) and removed one
assertion line from an existing test (no test-count change from that edit).
Both `pytest --collect-only` and a full local run confirm **463 passed**,
matching the correctly-attributed CI run for this commit. No test
collection defect exists; no additional tests were needed.

H1 and H3 remain fixed; this checkpoint made no changes to
`deployment_validation.py`, `text_normalization.py`, `rules.py`, or any
auth/isolation code. Hosted staging and real WorkOS login validation
remain incomplete, as stated above.
