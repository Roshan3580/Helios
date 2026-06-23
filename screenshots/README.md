# Screenshots

Real UI captures for the portfolio README and Loom demo.

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

## Re-capture checklist

1. Backend on `:8000`, `curl -X POST http://localhost:8000/v1/demo/seed`
2. Frontend: `VITE_HELIOS_DEMO_MODE=false`, `bun dev`
3. Optional: run SDK demo for a fresh trace before trace-detail capture
4. Capture at 1280×720 or 1440×900
