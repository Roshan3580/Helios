# Helios Project Improvements

Prioritized backlog and phase completion status.

---

## Phase completion

| Phase         | Scope                                                                    | Status       |
| ------------- | ------------------------------------------------------------------------ | ------------ |
| **Phase 1**   | FastAPI backend, Postgres models, Alembic, trace/project APIs, demo seed | **Complete** |
| **Phase 2**   | Frontend API client, traces pages wired, demo fallback                   | **Complete** |
| **Phase 3**   | Dashboard, RAG, evals, prompts, datasets read APIs + frontend wiring     | **Complete** |
| **Phase 4**   | Python SDK, external RAG demo app, real trace ingestion                  | **Complete** |
| **Phase 5**   | Public demo polish — README, diagrams, screenshots, demo script          | **Complete** |
| **Phase 5.5** | Real screenshots, portfolio README polish, demo-only UI actions          | **Complete** |

---

## P0 — Critical path

| Item                     | Description                    | Status |
| ------------------------ | ------------------------------ | ------ |
| Backend API scaffold     | FastAPI, CORS, project scoping | Done   |
| Database schema          | Traces, spans, projects        | Done   |
| Trace ingestion          | `POST /v1/traces`              | Done   |
| Trace list + detail APIs | Filterable list, span tree     | Done   |
| Frontend API integration | Live fetch + demo fallback     | Done   |
| Environment config       | `VITE_API_BASE_URL`, demo mode | Done   |

---

## P1 — Core product features

| Item                   | Description                     | Status              |
| ---------------------- | ------------------------------- | ------------------- |
| Dashboard metrics API  | Aggregates from trace/eval data | Done (sample scale) |
| RAG analytics read API | Chunk metrics + aggregates      | Done (sample scale) |
| Evaluations read API   | Seeded eval runs                | Done                |
| Prompts read API       | Seeded prompt versions          | Done                |
| Datasets read API      | Derived from eval runs          | Done                |
| External trace demo    | RAG support bot via SDK         | Done                |
| Eval runner            | Async worker for eval suites    | Not started         |
| Prompt CRUD            | Immutable version history       | Not started         |
| Dataset upload         | JSONL import                    | Not started         |

---

## P2 — Platform and polish

| Item                    | Description                                 | Status      |
| ----------------------- | ------------------------------------------- | ----------- |
| Python SDK              | `helios_sdk` trace ingestion                | Done (demo) |
| Portfolio README        | Screenshots, architecture, demo flow        | Done        |
| Architecture diagrams   | Mermaid component, lifecycle, deployment    | Done        |
| Demo walkthrough script | [DEMO_SCRIPT.md](DEMO_SCRIPT.md)            | Done        |
| TypeScript SDK          | Node/browser client                         | Not started |
| Auth                    | API keys, project membership                | Not started |
| OpenTelemetry           | Exporter compatibility                      | Not started |
| CI/CD                   | GitHub Actions lint/build/test              | Not started |
| Real screenshots        | Portfolio README captures in `screenshots/` | Done        |
| Demo-only UI actions    | Placeholder notice for create/run buttons   | Done        |
| Loom demo video         | Record using demo script                    | Not started |

---

## Notes

- Frontend visual design is approved — do not redesign
- Demo fallback must remain behind `VITE_HELIOS_DEMO_MODE=true`
- Real screenshots live in `screenshots/` — see [screenshots/README.md](../screenshots/README.md)
- Create/run header buttons show a demo-only notice (no fake navigation)
- See [DEMO_SCRIPT.md](DEMO_SCRIPT.md) for 90-second walkthrough

---

## Next priorities (post Phase 5.5)

1. Record Loom walkthrough ([DEMO_SCRIPT.md](DEMO_SCRIPT.md))
2. API key auth for ingestion
3. Eval runner with background workers
4. TypeScript SDK
5. GitHub Actions CI
