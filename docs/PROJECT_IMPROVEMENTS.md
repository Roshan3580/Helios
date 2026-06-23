# Helios Project Improvements

Prioritized backlog for taking Helios from frontend prototype to production-ready platform.

## P0 — Critical path

| Item                     | Description                                              | Status |
| ------------------------ | -------------------------------------------------------- | ------ |
| Backend API scaffold     | FastAPI project with health check, CORS, project scoping | Done   |
| Database schema          | PostgreSQL tables for traces, spans, projects            | Done   |
| Trace ingestion          | POST endpoint accepting OTel-style span batches          | Done   |
| Trace list API           | Paginated, filterable trace query                        | Done   |
| Trace detail API         | Span tree reconstruction                                 | Done   |
| Frontend API integration | Replace demo data in traces pages with live fetch        | Done   |
| Environment config       | Wire `VITE_API_BASE_URL` in frontend client              | Done   |

## P1 — Core product features

| Item                   | Description                                         | Status        |
| ---------------------- | --------------------------------------------------- | ------------- |
| Eval runner            | Async worker executing eval suites against datasets | Not started   |
| Prompt versioning      | CRUD, immutable versions, diff metadata             | Not started   |
| RAG analytics pipeline | Aggregate retrieval metrics from span attributes    | Not started   |
| Cost tracking          | Token and cost aggregation from span attributes     | Not started   |
| Dashboard metrics      | Real overview stats from trace data                 | Done (sample) |
| Dataset management     | Upload and manage eval datasets                     | Not started   |
| External trace demo    | RAG support bot submitting traces via SDK           | Done          |

## P2 — Platform and polish

| Item             | Description                                    | Status      |
| ---------------- | ---------------------------------------------- | ----------- |
| Python SDK       | Lightweight `helios_sdk` for trace ingestion   | Done (demo) |
| TypeScript SDK   | Client library for Node/browser apps           | Not started |
| Auth             | API keys, project membership                   | Not started |
| Deployment       | Docker Compose, production hosting guide       | Not started |
| Monitoring       | Backend health, ingestion rate, error alerting | Not started |
| Lint/format CI   | GitHub Actions for lint, build, typecheck      | Not started |
| Documentation    | API reference, SDK guides, onboarding          | Not started |
| Screenshots      | Capture and add to README                      | Not started |
| Typecheck script | Add `tsc --noEmit` to package.json             | Not started |

## Notes

- Frontend visual design is approved — do not redesign during backend integration
- Demo data should remain available behind `VITE_HELIOS_DEMO_MODE=true` for local development without backend
- Prefer incremental integration: one page at a time, starting with traces
