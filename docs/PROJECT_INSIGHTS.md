# Project Insights (Deterministic Project-Window Analysis)

Ruleset version: **`project-window-v1`**

Helios can analyze one authorized project across a time window and compare it
against the immediately preceding equal-length window, producing bounded,
deterministic, evidence-linked findings from canonical OpenTelemetry data. It
is synchronous, ephemeral (nothing persisted), organization-authorized,
content-excluding, and deterministic-first: an optional narrative may explain
findings, but never creates or alters them.

Package: `backend/app/project_analyst/`

| Module | Role |
| ------ | ---- |
| `models.py` | Windows, findings, coverage, bounds, query-evidence types |
| `thresholds.py` | Versioned rule thresholds and hard bounds |
| `queries.py` | Bounded SQL evidence collection (aggregates + capped examples) |
| `evidence.py` | Deterministic evidence IDs, signature redaction, finding builder |
| `rules.py` | Pure rule implementations over collected evidence |
| `runner.py` | `analyze_project_window(db, project_id=…, hours=…, as_of=…, rules=…)` |
| `serializer.py` | API response conversion + narrative bundle serialization |
| `narrative.py` | Optional narrative attachment (reuses the Checkpoint 10 layer) |

Flow: authorized project → bounded SQL evidence queries → deterministic
project-window rules → `ProjectFinding[]` → optional existing narrative
provider → authenticated API response.

## Window semantics

- Request parameter: `hours` (default `24`, min `1`, max `720`).
- `as_of` is selected **once at request start in UTC** and is not
  client-suppliable in this release.
- Current window: `[as_of - hours, as_of)` — start inclusive, end exclusive.
- Baseline window: `[as_of - 2*hours, as_of - hours)`.
- Window membership uses trace `start_time`; span-level queries join through
  the project-scoped traces in the window.
- Every query in one request binds the same `as_of`, `project_id`, and the
  exact window boundaries; the resolved boundaries are returned verbatim.

## Bounded query strategy

Aggregate metrics (counts, error rates, PostgreSQL `percentile_cont`
percentiles, token sums) cover **all** matching rows. Only example traces,
per-entity breakdowns, and the error-span candidate set are capped
(`thresholds.py`), and the response reports whether any cap actually
truncated:

| Bound | Value |
| ----- | ----- |
| `MAX_PROJECT_FINDINGS` | 50 |
| `MAX_EXAMPLE_TRACES_PER_FINDING` | 5 |
| `MAX_SERVICES_ANALYZED` | 100 (by current-window trace count, then name) |
| `MAX_MODELS_ANALYZED` | 100 (by current-window span count, then name) |
| `MAX_ERROR_GROUPS` | 50 (by occurrences, then signature) |
| `MAX_ERROR_SPAN_CANDIDATES` | 500 (newest ERROR spans loaded for clustering) |

`MAX_ERROR_SPAN_CANDIDATES` replaces the suggested `MAX_CANDIDATE_TRACES`:
error-span clustering is the only place where rows (rather than SQL
aggregates) are pulled into Python, so it is the bound that matters.

Implementation guarantees: every query binds `project_id` and both window
boundaries; per-service/per-model examples come from single window-function
queries (no N+1); token/model values are read from JSONB with
`jsonb_typeof` guards so malformed values are ignored, never estimated; all
orderings carry deterministic tie-breakers.

## Finding model

Each `ProjectFinding` carries: deterministic `evidence_id` (`pev_…`, stable
for identical project/window/evidence/ruleset input), `rule_id`,
`ruleset_version`, severity (`error`/`warning`/`info`), confidence
(`high`/`medium`/`low`), category, factual `statement` (never causal),
`metric_name`, observed/baseline values, both windows, an affected entity
(`service` | `model` | `error_signature` | `instrumentation` | `project` +
label), bounded supporting trace references, optional supporting span IDs,
sample sizes, and safe supporting values.

A supporting trace reference contains only real, browser-safe values: trace
ID, service, root span name, start time, duration, span count, error count,
and `/app/traces/{trace_id}`. Every cited trace belongs to the authorized
project (defensively re-validated in the runner); every cited span belongs to
a cited cluster/example. Findings sort by severity → rule ID → entity label →
evidence ID.

## Rules (`project-window-v1`)

| Rule ID | Minimum sample | Trigger | Severity | Confidence |
| ------- | -------------- | ------- | -------- | ---------- |
| `service_error_rate_regression` | ≥10 traces per window per service | +10pp error-rate increase AND ≥1.5× baseline rate (zero baseline: ≥3 current error traces) | warning (+10–24.99pp) / error (≥+25pp) | high ≥30 traces per window, else medium |
| `service_latency_regression` | ≥10 traces per window | current p95 ≥1.5× baseline p95 AND +≥100ms AND current p95 > 0 | warning (1.5–1.99×) / error (≥2×; baseline p95 = 0 counts as error) | high ≥30 per window, else medium |
| `model_latency_regression` | ≥10 model-attributed spans per window | same factors on span p95 (model = `gen_ai.request.model` else `gen_ai.response.model`; unattributed spans never grouped as "unknown") | as above | as above |
| `model_token_usage_regression` | ≥10 token-reporting spans per window | avg recorded total tokens/span ≥1.5× baseline AND +≥500 | warning | high ≥30 token spans per window, else medium |
| `trace_latency_outliers` | ≥20 current traces | traces ≥ max(2× current p95, 500ms); one project-level finding | warning / error (max ≥4× p95) | high |
| `recurring_error_cluster` | ≥3 ERROR spans across ≥2 traces per signature | signature = span name + bounded normalized status message + bounded `exception.type` | warning (3–9) / error (≥10) | high with status/exception info, else medium |
| `genai_instrumentation_gap` | ≥5 model-like spans | ≥20% missing model identity or ≥20% missing both token attrs | info (20–49.99%) / warning (≥50%) | high when all model-like spans are explicitly classified (`helios.span.type="llm"` or OpenAI instrumentation scope), else medium |
| `error_concentration_by_service` | ≥5 current error traces, ≥2 services observed | one service ≥70% of project error traces | warning / error (≥90% and ≥10 service error traces) | high |

False-positive guards: minimum samples suppress every regression rule; the
relative-factor requirement prevents small-absolute-rate noise; outliers
require both a relative (2× p95) and absolute (500ms) floor so p95-level
traces are not flagged; token averages use only recorded numeric values.

Error-signature redaction (`normalize_status_message`): whitespace collapsed,
digit runs → `#`, tokens longer than 24 chars → `<long>` (keys, JWTs, hashes,
UUIDs), bounded to 64 chars. Full exception messages, stack traces, prompts,
tool output, and secrets never enter signatures, and the normalized message
appears only in structured evidence — never interpolated into statements.

## Deliberately unsupported

No rules exist for: model/infrastructure cost, prompt regressions, retrieval
score regressions, duplicate retrieval content, citation quality,
hallucination detection, evaluation regressions, automated root-cause
certainty, deployment correlation, user-impact estimation, SLO compliance (no
SLO model exists), or project-wide repeated-tool-call analysis (deferred until
a bounded, defensible query design exists). Every response states the
mandatory limitations, including workload-mix and sparse-baseline caveats,
even with zero findings.

## Authenticated API

```http
POST /v2/user/projects/{project_ref}/analysis
Authorization: Bearer <WorkOS access token>
Content-Type: application/json

{ "hours": 24, "rules": null, "include_narrative": false }
```

- Missing/invalid JWT → `401`; unlinked organization → `403`;
  inaccessible/cross-organization project → `404` (indistinguishable from
  missing — never reveals other organizations' projects). Project API keys are
  never accepted.
- `hours`: 1–720, default 24. `rules`: omitted/null = all defaults; non-empty
  subset allowed (duplicates deduplicated first-seen); `[]` or unknown IDs →
  `422`. `extra="forbid"`: no prompt, question, instructions, provider, model,
  thresholds, `as_of`, project override, or content option.
- Response (`ProjectAnalysisRead`): `analysis_version="project-window-v1"`,
  `mode="deterministic"`, `project_id`, `generated_at`, `hours`, exact
  `current_window`/`baseline_window`, `findings`, `coverage`, `limitations`,
  `available_rules`, `executed_rules`, `bounds` (caps + truncation flags),
  `narrative_status`, optional validated `narrative`.
- Coverage reports factual counts only (trace/span/error counts per window,
  services/models observed, model-like/token/tool-like spans, traces without a
  root span, orphan spans, sparse-sample flags) — never a quality score or an
  invented completeness percentage.

The single-trace route `POST …/analysis/traces/{trace_id}` is unchanged.

## Optional narrative

Reuses the Checkpoint 10 provider layer (same config gates, same single
OpenAI adapter, same post-validation binding prose to existing evidence IDs;
see [ADR_005](ADR_005_OPTIONAL_ANALYST_NARRATIVE.md)). The project bundle
(`ProjectNarrativeEvidenceBundle`) contains only: analysis version, window
hours/boundaries, coverage counts, limitations, and bounded sanitized findings
(evidence ID, rule, severity, confidence, category, statement,
observed/baseline, entity label, bounded metadata). It **excludes** project
names, organization/user identity, trace IDs, span IDs, raw traces/spans,
prompts, completions, events, links, tool arguments/output, documents, JWTs,
and API keys — deterministic frontend trace links live outside the narrative
path. Failure yields `narrative_status="failed"` with deterministic findings
intact. Disabled by default; explicit request plus explicit third-party opt-in
required; only fake providers in tests.

## Frontend: `/app/insights`

Navigation: **Observe → Insights** in the app shell. The page shows the
selected project/environment, a time selector (24h / 7d / 30d), and an
explicit **Analyze project** button (**Run again** after success, optional
**Generate explanation**). No free-form prompt, provider/model selector,
threshold controls, or analysis on page entry.

Results (`src/components/helios/project-analysis-panel.tsx`,
`project-finding-card.tsx`, `src/hooks/use-project-analysis.ts`,
`src/lib/analyst/project-format.ts`):

- summary strip (finding/severity counts), data-coverage section (both
  windows, truncation notice when caps applied — coverage is never a score),
- finding cards with text severity, rule label, category, confidence, factual
  statement, observed/baseline, entity, sample size, collapsible safe
  supporting values, and real supporting-trace links to `/app/traces/{id}`
  (backend-provided references only; provider-created links are never
  rendered),
- narrative remains secondary and evidence-ID-bound; failure preserves the
  deterministic UI,
- results live only in React memory and clear on project/organization/hours
  change and unmount; superseded requests are aborted; 401 redirects through
  AuthKit; 403/404/422/network states show safe copy with retry; no demo
  fallback and no local/session storage,
- zero findings shows: "No findings were produced by the current
  project-window rule set." — the project is never declared healthy.

## Non-goals of this release

No persistence, analysis history, background workers, queues, cron, scheduled
monitoring or alerts, caching layer, new database tables/migrations, second
narrative provider, or real provider calls in CI/tests. Known limitation:
current-vs-baseline comparisons are sensitive to workload-mix changes and
sparse baselines; findings are investigative starting points, not root-cause
determinations.
