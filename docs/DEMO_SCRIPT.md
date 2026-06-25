# Helios: 90-Second Demo Script

Use this script for a Loom walkthrough. Target length: **90 seconds**. Speak in short sentences; show the UI, not slides.

---

## 0:00: Hook (10s)

> "Helios is an observability console for LLM apps: traces, RAG quality, evals, and prompts in one place. I'll show the UI, then prove external trace ingestion with a Python SDK."

**Show:** `screenshots/landing-page.png` or live `/`

---

## 0:10: Dashboard (12s)

> "The dashboard summarizes requests, latency, tokens, cost, and error rate from live backend data. Recent traces link straight into detail views."

**Show:** `/app/dashboard` (live API mode: `VITE_HELIOS_DEMO_MODE=false`)

**Point at:** metric cards, recent traces list

---

## 0:22: Traces list (10s)

> "Every request is a trace. I can filter and open any row to inspect spans."

**Show:** `/app/traces`

**Point at:** trace ID, query, model, latency, status badges

---

## 0:32: Trace detail (12s)

> "Trace detail shows a nested span timeline: input, retrieval, LLM, tools, and output. This is the core debugging surface for agents and RAG."

**Show:** `/app/traces/<trace_id>` (seeded or SDK trace)

**Point at:** span timeline, header metrics

---

## 0:44: RAG analytics (10s)

> "RAG analytics aggregates retrieval hit rate, citation coverage, chunk quality, and missed queries."

**Show:** `/app/rag-analytics`

---

## 0:54: SDK + external app (18s)

> "Traces don't only come from seed data. Here's a lightweight Python SDK and a deterministic RAG support bot."

**Show:** Terminal: `examples/rag_support_bot/run_demo.py` output with `trace_id`

**Say:** "The app simulates retrieval and LLM steps, then POSTs spans to `/v1/traces`."

---

## 1:12: New trace appears (10s)

> "Refresh the traces page; the SDK trace is here. Open it; same span tree, persisted in Postgres."

**Show:** `/app/traces` → click new `trc_...` row → detail page

---

## 1:22: Close (8s)

> "Helios is a portfolio project: FastAPI backend, React frontend, PostgreSQL, and SDK ingestion. Auth, workers, and OpenTelemetry are future work. Repo link in the description."

**Show:** GitHub repo or architecture diagram from README

---

## Pre-recording checklist

- [ ] Backend running on `:8000`, Postgres up
- [ ] `curl -X POST http://localhost:8000/v1/demo/seed`
- [ ] Frontend: `VITE_HELIOS_DEMO_MODE=false`, `bun dev`
- [ ] SDK demo venv ready: `pip install -r examples/rag_support_bot/requirements.txt`
- [ ] Browser zoom 100%, clean window, no personal tabs
