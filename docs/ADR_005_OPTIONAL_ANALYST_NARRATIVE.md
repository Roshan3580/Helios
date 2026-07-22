# ADR 005 — Optional Analyst Narrative

**Status:** Accepted  
**Date:** 2026-07-19  
**Branch:** `helios-v2-otel-foundation`

## Context

Checkpoint 8 shipped a pure deterministic single-trace evidence engine.
Checkpoint 9 exposed that engine through an authenticated API and the
trace-detail UI. Operators still benefit from short prose that explains why
findings matter, but generative text must never become a second source of
facts.

## Decision

Add an **optional, evidence-constrained narrative layer** behind explicit
feature flags. Deterministic findings remain the source of truth:

```text
Canonical telemetry
  → deterministic evidence engine
  → Evidence[]
  → optional narrative provider
  → prose constrained to existing evidence IDs
```

### Provider-neutral interface

`backend/app/analyst_narrative/` defines:

- `NarrativeProvider` protocol (`async generate(bundle=...)`)
- sanitized `NarrativeEvidenceBundle` serializer
- post-provider validation
- orchestration that never mutates deterministic findings

Concrete adapters live under `providers/`. The initial adapter is OpenAI only.

### Initial provider decision

| Item | Choice |
| ---- | ------ |
| Provider | OpenAI |
| SDK | official `openai` Python package `>=2.46.0,<3` (verified on PyPI as 2.46.0 on 2026-07-17) |
| API | Responses API |
| Structured output | `AsyncOpenAI.responses.parse(..., text_format=ProviderNarrative)` with strict schema adherence |
| Persistence request | `store=False` |
| Retries | SDK `max_retries=0`; Helios retries at most once for rate-limit / 5xx |
| Anthropic | Not implemented in this checkpoint (also has structured outputs, deferred to keep one production adapter) |

Official docs reviewed:

- https://developers.openai.com/api/docs/guides/structured-outputs
- https://developers.openai.com/api/reference/resources/responses/
- https://platform.openai.com/docs/guides/your-data
- https://pypi.org/project/openai/
- https://platform.claude.com/docs/en/build-with-claude/structured-outputs (evaluated, not selected)

### Configuration

Server-only (never `VITE_*`):

| Variable | Default | Role |
| -------- | ------- | ---- |
| `HELIOS_ANALYST_NARRATIVE_ENABLED` | `false` | Master feature flag |
| `HELIOS_ANALYST_ALLOW_THIRD_PARTY` | `false` | Explicit opt-in to send evidence metadata externally |
| `HELIOS_ANALYST_PROVIDER` | `""` | Must be `openai` when enabling |
| `HELIOS_ANALYST_MODEL` | `""` | Explicit model required |
| `HELIOS_ANALYST_TIMEOUT_SECONDS` | `20` | Per-call timeout |
| `HELIOS_ANALYST_MAX_OUTPUT_TOKENS` | `1200` | Provider output bound |
| `HELIOS_ANALYST_MAX_EVIDENCE_BYTES` | `24000` | Provider input bound |
| `HELIOS_ANALYST_MAX_FINDINGS` | `25` | Max findings in provider payload |
| `OPENAI_API_KEY` | empty | Provider credential (`SecretStr`) |

Narrative runs only when **both** enablement flags are true **and** provider,
model, and API key are configured. Incomplete configuration yields
`narrative_status="disabled"` without failing process startup or CI.

### Request / response

Additive request field: `include_narrative` (default `false`).

Additive response fields:

- `narrative_status`: `not_requested` | `disabled` | `complete` | `failed`
- `narrative`: `{ summary, finding_explanations[], caveats[] }` or `null`

Provider failures never become HTTP 500 when deterministic analysis succeeded.

### Safety invariants

- Provider receives only a sanitized evidence bundle (no raw OTel detail,
  identity, credentials, prompts, completions, tool I/O, or documents).
- Telemetry-derived text is delimited as data, not instructions.
- Every returned `evidence_id` must exist in deterministic findings.
- Output validation rejects URLs, HTML, secret-like patterns, and unsupported
  affirmative claims (cost / RAG / citation / hallucination / evaluation /
  prompt quality). Documentary limitation wording remains allowed.
- Frontend renders narrative as plain text; navigation uses deterministic
  span IDs only.

### Non-goals

- No persistence / history / queue / worker
- No project-wide analysis
- No arbitrary user prompts
- No cost / RAG / citation / hallucination / evaluation analysis
- No claim of Zero Data Retention unless the deployed OpenAI organization is
  actually configured for it (`store=False` is requested per call; ZDR is an
  account-level control)

## Consequences

- Deterministic analysis remains fully usable when narrative is off or fails.
- Operators must consciously enable third-party transmission.
- A future Anthropic (or other) adapter can implement the same protocol
  without changing the public API contract.
- Prompt-injection risk is mitigated in layers (redaction, delimited data,
  schema, validation) but not claimed solved.
