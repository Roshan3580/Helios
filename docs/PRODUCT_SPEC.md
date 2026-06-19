# Helios Product Specification

## Product problem

Developers building production LLM applications lack purpose-built observability tooling. Traditional APM captures HTTP requests but not the nested structure of agent runs, RAG retrievals, prompt versions, or evaluation scores. Debugging failures requires manual log correlation across multiple systems.

Helios aims to provide a single console for tracing, evaluating, and optimizing AI systems.

## Target users

- **AI/ML engineers** shipping agents, RAG pipelines, or LLM-powered features
- **Platform teams** operating shared LLM infrastructure across multiple products
- **Applied researchers** running prompt experiments and model comparisons

## Core user journeys

### 1. Debug a failed agent run

1. Open Traces list, filter by status=error
2. Click trace to view span tree
3. Inspect failed LLM call or tool invocation
4. Replay with same inputs (planned)

### 2. Compare prompt versions

1. Navigate to Prompts
2. Select prompt, view version history
3. Compare v(N) vs v(N+1) on latency, cost, eval score
4. Promote winning version (planned)

### 3. Run an evaluation suite

1. Create or select dataset
2. Configure evaluators (deterministic, LLM-judge, code)
3. Run against prompt version + model
4. Review per-case results and aggregate scores

### 4. Monitor RAG quality

1. Open RAG Analytics dashboard
2. Review hit rate, citation coverage trends
3. Drill into traces with missing sources
4. Identify retrieval configuration issues

## Main entities

| Entity | Description |
|--------|-------------|
| **Project** | Top-level container for traces, prompts, evals |
| **Trace** | Single end-to-end request/run |
| **Span** | Individual step within a trace |
| **Prompt** | Named prompt template with version history |
| **Prompt Version** | Immutable snapshot of prompt content + metadata |
| **Dataset** | Collection of input/expected-output pairs for evals |
| **Eval Suite** | Dataset + prompt + evaluators configuration |
| **Eval Run** | Single execution of an eval suite |
| **Experiment** | Side-by-side comparison of configurations |

## Screens / pages

### Marketing (implemented)

- Landing page with hero, platform overview, how-it-works, trace preview, evaluations table, RAG section, SDK CTA, footer

### App console (implemented with demo data)

| Route | Page |
|-------|------|
| `/app/dashboard` | Overview metrics and recent traces |
| `/app/traces` | Trace list with filters |
| `/app/traces/:id` | Trace detail with span tree |
| `/app/prompts` | Prompt list and version info |
| `/app/evaluations` | Eval suite results |
| `/app/rag-analytics` | RAG quality metrics |
| `/app/experiments` | Experiment comparisons |
| `/app/datasets` | Dataset management |
| `/app/settings` | Project settings |

## Non-goals (current phase)

- Multi-tenant auth and billing
- Real-time streaming trace ingestion UI
- Model hosting or inference
- Prompt playground / inline editing with live model calls
- Datadog / Grafana export integrations
- On-prem deployment guides

These may be considered in later phases after core backend and SDK are stable.
