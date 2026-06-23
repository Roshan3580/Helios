# Screenshot placeholders

PNG files in this directory are **placeholder images** for the portfolio README. Replace them with real captures before publishing or recording a Loom demo.

## Recommended capture flow

1. Start backend + frontend with `VITE_HELIOS_DEMO_MODE=false`
2. Seed demo data: `curl -X POST http://localhost:8000/v1/demo/seed`
3. Run SDK demo for a fresh trace: `python examples/rag_support_bot/run_demo.py`
4. Capture at 1280×720 (or 1440×900) from browser / terminal

| File                | Route / subject                     |
| ------------------- | ----------------------------------- |
| `landing-page.png`  | `/`                                 |
| `dashboard.png`     | `/app/dashboard`                    |
| `traces.png`        | `/app/traces`                       |
| `trace-detail.png`  | `/app/traces/trc_...`               |
| `rag-analytics.png` | `/app/rag-analytics`                |
| `evaluations.png`   | `/app/evaluations`                  |
| `prompts.png`       | `/app/prompts`                      |
| `datasets.png`      | `/app/datasets`                     |
| `sdk-demo.png`      | Terminal output after `run_demo.py` |
