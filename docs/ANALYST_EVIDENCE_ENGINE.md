# Deterministic Trace Evidence Engine

Ruleset version: **`single-trace-v1`**

Helios includes a pure, deterministic single-trace analyst engine that turns
canonical OpenTelemetry trace detail into typed, evidence-backed findings. It
is exposed to authenticated users through a human-authenticated API route and
the trace-detail UI (see below). There is **no** LLM narration: every result is
computed by fixed rules over stored telemetry.

## Canonical evidence sources

The engine analyzes only:

- `otel_traces` / `otel_spans` fields as exposed by
  `OtelTraceDetailRead` (`backend/app/schemas_v2.py`)
- span attributes that callers/SDK actually stored

It never reads legacy `/v1/*` stores, seed/demo data, prompt/eval/RAG tables, or
fabricated cost fields.

Package: `backend/app/analyst/`

| Module | Role |
| ------ | ---- |
| `models.py` | Finding / result types, severity/confidence/category |
| `thresholds.py` | Versioned numeric thresholds |
| `redaction.py` | Safe attribute reads, allowlists, secret/content exclusion |
| `hierarchy.py` | Parent/child graph, orphans, cycles |
| `evidence.py` | Deterministic evidence IDs and finding construction |
| `rules.py` | Rule implementations |
| `runner.py` | `analyze_trace(...)` |

Entry point: `from app.analyst import analyze_trace`.

## Severity and confidence

| Severity | Meaning |
| -------- | ------- |
| `error` | Reliability failure or extreme latency concentration (≥80%) |
| `warning` | Notable inefficiency or instrumentation cycle |
| `info` | Instrumentation gaps, serial observation, moderate signals |

| Confidence | Meaning |
| ---------- | ------- |
| `high` | Direct status/timing/hierarchy facts |
| `medium` | Heuristic grouping (tool/model siblings, serial intervals) |
| `low` | Reserved (unused in `single-trace-v1`) |

Categories: `performance`, `reliability`, `efficiency`, `instrumentation`.

## Attribute safety

Recognized classification keys (when present):

- `helios.span.type`
- `tool.name`
- `gen_ai.operation.name`
- `gen_ai.request.model` / `gen_ai.response.model`
- `gen_ai.usage.input_tokens` / `gen_ai.usage.output_tokens`

Supporting attributes on findings are allowlisted, length-bounded (64 chars for
strings), and exclude secret-like keys (`authorization`, `api_key`, `password`,
`token`, `cookie`, `session`, `credential`, …) and content-like keys (prompts,
completions, tool results/arguments, retrieval documents/queries, …).

Status messages may appear in supporting attributes (bounded) but are **not**
interpolated into factual statements.

Missing token values are never estimated (no 75/25 split).

## Hierarchy handling

`build_hierarchy` preserves spans, detects multiple roots, orphans (non-null
parent missing from the trace), and cycles (deduplicated, canonically rotated).
Children are ordered by `(start_time, span_id)`. Input objects are never mutated.

## Rules (`single-trace-v1`)

| Rule ID | Thresholds | Severity | Confidence |
| ------- | ---------- | -------- | ---------- |
| `error_span` | `status_code == 2` | error | high |
| `failing_child_transition` | ERROR child under non-ERROR known parent | error | high |
| `latency_concentration` | longest non-root ≥50% of trace (warn), ≥80% (error) | warning/error | high |
| `repeated_sibling_tool_calls` | ≥3 tool-like siblings, same parent + identity | warning | medium |
| `repeated_sibling_model_calls` | ≥3 model-like siblings, same parent + model/op | warning | medium |
| `serial_sibling_operations` | ≥3 tool/model siblings, no material overlap (1ms tol), ≥60% parent (info), ≥85% (warning) | info/warning | medium |
| `missing_genai_telemetry` | model-like missing model and/or tokens | info | high if `helios.span.type=llm`, else medium |
| `orphan_span_parent` | parent id absent from trace | info | high |
| `cyclic_span_hierarchy` | one finding per unique cycle | warning | high |

Tool-like: `helios.span.type == "tool"` or non-empty `tool.name`.  
Model-like: type `llm`, or request/response model, or `gen_ai.operation.name`.

## Runner behavior

```python
analyze_trace(project_id=..., trace_detail=..., rules=None) -> TraceAnalysisResult
```

- Default runs all registered rules; unknown rule IDs raise `AnalystValidationError`.
- Findings sorted by severity → rule_id → first span start → evidence_id.
- Evidence IDs are deterministic for identical inputs and ruleset version.
- Coverage summary counts spans, errors, model/token/tool/model-like/orphans.
- Mandatory limitations always include unavailability of cost, RAG quality,
  citations, evaluations, and content-based prompt/response analysis.
- No DB access inside rules; no network; no logging of telemetry content.

## Unsupported conclusions

The engine does **not** produce findings for:

- model cost
- RAG quality / retrieval scores
- citation quality
- hallucination detection
- evaluation regressions
- prompt quality (content is not inspected)

## Authenticated analysis API

```http
POST /v2/user/projects/{project_ref}/analysis/traces/{trace_id}
Authorization: Bearer <WorkOS access token>
Content-Type: application/json
```

- **Authentication:** WorkOS human JWT only (`require_org_member`); a project
  API key is never accepted and never minted by this path.
- **Authorization:** the project is resolved by UUID or slug strictly inside
  the caller's linked organization; inaccessible projects, cross-organization
  projects, and missing traces are all `404` (indistinguishable). Missing or
  invalid JWT → `401`; unlinked organization → `403`.
- **Execution:** synchronous and deterministic. Results are ephemeral — no
  table, queue, worker, or cache stores them.

### Request (`TraceAnalysisRequest`)

```json
{ "rules": null }
```

| `rules` value | Behavior |
| ------------- | -------- |
| omitted / `null` | run every default `single-trace-v1` rule |
| non-empty list | run only those rules (duplicates deduplicated, first occurrence wins) |
| `[]` | rejected with `422` |
| unknown rule ID | rejected with `422` |
| any other field | rejected with `422` (`extra="forbid"`) |

Callers cannot override the project, trace, ruleset version, severity, or
thresholds, and there is no `include_content` / prompt / instruction field.

### Response (`TraceAnalysisRead`)

Top level: `analysis_version` (`"single-trace-v1"`), `mode`
(`"deterministic"`), `project_id`, `trace_id`, `generated_at`, `findings`,
`coverage`, `limitations`, `available_rules`, `executed_rules`.

Findings carry the engine's deterministic `evidence_id`, rule/severity/
confidence/category, factual `statement`, `metric_name`,
`observed_value`/`baseline_value`, cited `span_ids`, source timestamps,
allowlisted `supporting_attributes`, `trace_ui_path`, and `span_ui_selectors`
(`span:<span_id>`). The mandatory limitations are always returned, even with
zero findings. Nothing beyond the engine's redaction layer is exposed.

Layering: router (`routers/user_v2.py`) → application service
(`services/trace_analysis_service.py`, no network/writes) → pure engine
(`app/analyst`). `AnalystValidationError` maps to `422`.

## Trace-detail UI

`/app/traces/{trace_id}` includes a **Trace analysis** panel
(`src/components/helios/trace-analysis-panel.tsx` +
`src/hooks/use-trace-analysis.ts`):

- analysis runs only when the user clicks **Analyze trace** (rerun via
  **Run again**); nothing runs automatically on page load
- results live only in React memory and are cleared when the project, trace,
  or organization changes
- activating a finding selects the first valid cited span in the existing
  waterfall/span inspector (span IDs are validated against the loaded trace);
  multi-span findings expose each cited span
- coverage counts and the mandatory limitations are always displayed
- zero findings shows truthful copy — the trace is not declared healthy

## Optional narrative layer

An optional provider-backed narrative may explain existing evidence IDs when
explicitly requested (`include_narrative: true`) and when both
`HELIOS_ANALYST_NARRATIVE_ENABLED` and `HELIOS_ANALYST_ALLOW_THIRD_PARTY` are
enabled with a configured provider/model/key. See
[ADR_005_OPTIONAL_ANALYST_NARRATIVE.md](ADR_005_OPTIONAL_ANALYST_NARRATIVE.md).

Narrative statuses: `not_requested` | `disabled` | `complete` | `failed`.
Provider failure never suppresses deterministic findings. Narrative is
disabled by default and is not required for CI or local development.
