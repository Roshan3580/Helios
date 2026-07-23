#!/usr/bin/env bash
# Free invited-beta configuration contract — runs locally and in CI with no
# platform credentials and no network access. Validates only committed files
# and source contracts (Checkpoint 24). Never deploys.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[free-beta] validating .env.beta.example + docs + source contracts"

python3 - <<'PY'
import re
from pathlib import Path

fail = []


def require(cond, msg):
    if not cond:
        fail.append(msg)


# ---------------------------------------------------------------------------
# .env.beta.example must exist and encode the hardened, zero-cost contract.
# ---------------------------------------------------------------------------
beta = Path(".env.beta.example")
require(beta.exists(), ".env.beta.example is missing")
text = beta.read_text() if beta.exists() else ""

# Fail-closed flags (staging contract): demo/e2e/narrative all false.
require("HELIOS_DEMO_MODE=false" in text, "beta HELIOS_DEMO_MODE must be false")
require("HELIOS_E2E_TEST_MODE=false" in text, "beta HELIOS_E2E_TEST_MODE must be false")
require(
    "HELIOS_ANALYST_NARRATIVE_ENABLED=false" in text,
    "beta HELIOS_ANALYST_NARRATIVE_ENABLED must be false",
)
require(
    "HELIOS_ANALYST_ALLOW_THIRD_PARTY=false" in text,
    "beta HELIOS_ANALYST_ALLOW_THIRD_PARTY must be false",
)
require("VITE_HELIOS_DEMO_MODE=false" in text, "beta VITE_HELIOS_DEMO_MODE must be false")
require(
    "VITE_HELIOS_E2E_TEST_MODE=false" in text, "beta VITE_HELIOS_E2E_TEST_MODE must be false"
)

# No OpenAI key is required (narrative disabled): must not be an active assignment.
require(
    not re.search(r"^\s*OPENAI_API_KEY=\S", text, re.MULTILINE),
    "beta must not require an OPENAI_API_KEY (narrative disabled)",
)

# Exact CORS origin, no wildcard, HTTPS.
require(
    "CORS_ORIGINS=https://helios-staging-tau.vercel.app" in text,
    "beta CORS_ORIGINS must be the exact staging frontend origin",
)
require("CORS_ORIGINS=*" not in text and 'CORS_ORIGINS="*"' not in text, "wildcard CORS forbidden")

# Server-only WorkOS secrets must never be VITE_-prefixed (browser-exposed).
for secret in ("WORKOS_API_KEY", "WORKOS_COOKIE_PASSWORD"):
    require(
        f"VITE_{secret}" not in text,
        f"{secret} must be server-only, never VITE_-prefixed",
    )
# The WorkOS API key must be commented (dashboard-managed), never an active line.
require(
    not re.search(r"^\s*WORKOS_API_KEY=\S", text, re.MULTILINE),
    "WORKOS_API_KEY must be dashboard-managed (commented placeholder only)",
)

# Database URL must be a placeholder, never a real committed connection string.
require(
    not re.search(r"^\s*DATABASE_URL=postgres(?:ql)?://\S", text, re.MULTILINE),
    "DATABASE_URL must be a placeholder in the committed beta example",
)

# Cookie contract (Checkpoint 25): the misspelled/unconsumed WORKOS_COOKIE_SAMESITE
# must never be presented as a settable variable (an assignment, active or
# commented). A prose warning that it is NOT consumed is allowed.
require(
    re.search(r"WORKOS_COOKIE_SAMESITE\s*=", text) is None,
    "WORKOS_COOKIE_SAMESITE is not a consumed variable; do not document it as a setting",
)

# No real secret-like blobs (allow short docs placeholders / angle-bracket forms).
require(not re.search(r"sk_(?:test|live)_[A-Za-z0-9]{20,}", text), "secret-like WorkOS key found")
require(
    not re.search(r"hel_proj_[A-Za-z0-9]{8,}_[A-Za-z0-9+/=_-]{8,}", text),
    "project API key found in beta example",
)
require(not re.search(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.", text), "JWT found in beta example")

# ---------------------------------------------------------------------------
# Documentation must exist.
# ---------------------------------------------------------------------------
require(
    Path("docs/FREE_BETA_DEPLOYMENT.md").exists(),
    "docs/FREE_BETA_DEPLOYMENT.md is missing",
)

# ---------------------------------------------------------------------------
# render.yaml remains the PAID staging contract — beta must not repurpose it.
# main (not demo-v1) is the beta source branch.
# ---------------------------------------------------------------------------
render = Path("render.yaml").read_text()
require("helios-api-staging" in render, "render.yaml must remain the paid staging contract")
require("helios-api-beta" not in render, "beta service must not be added to render.yaml")
require(
    "branch: demo-v1" not in render,
    "render.yaml must not point at the demo-v1 branch",
)
require(
    "demo-v1" not in text,
    "beta example must not reference demo-v1 as the beta source branch",
)

doc = Path("docs/FREE_BETA_DEPLOYMENT.md").read_text()
require("helios-api-beta" in doc, "beta docs must describe the helios-api-beta service")
# The beta backend must build from `main` (the beta source branch), documented
# somewhere in the deployment doc (Markdown table cell or prose).
require(
    re.search(r"[Bb]ranch[^\n]*\bmain\b", doc) is not None,
    "beta docs must document `main` as the beta source branch",
)

if fail:
    print("[free-beta] FAILED:")
    for message in fail:
        print(f"  - {message}")
    raise SystemExit(1)

print("[free-beta] configuration contract OK")
PY

echo "[free-beta] OK"
