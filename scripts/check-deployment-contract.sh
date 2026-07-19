#!/usr/bin/env bash
# Local/CI deployment-contract validation — never deploys.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[deploy-contract] frontend unit tests"
bun test src/lib/api/base-url.test.ts src/lib/deploy/staging-guards.test.ts

echo "[deploy-contract] smoke script syntax"
bash -n scripts/smoke-staging.sh
bash -n scripts/scan-browser-bundle.sh

echo "[deploy-contract] render.yaml parse"
python3 - <<'PY'
import sys
from pathlib import Path
try:
    import yaml
except ImportError:
    # Minimal structural check without PyYAML.
    text = Path("render.yaml").read_text()
    assert "helios-api-staging" in text
    assert "preDeployCommand: alembic upgrade head" in text
    assert "healthCheckPath: /health/ready" in text
    assert "HELIOS_E2E_TEST_MODE" in text
    assert "sk_" not in text
    assert "hel_proj_" not in text
    print("render.yaml structural OK (no PyYAML)")
    sys.exit(0)
data = yaml.safe_load(Path("render.yaml").read_text())
assert data["services"][0]["healthCheckPath"] == "/health/ready"
assert data["services"][0]["preDeployCommand"] == "alembic upgrade head"
blob = Path("render.yaml").read_text()
assert "sk_test" not in blob and "sk_live" not in blob
print("render.yaml OK")
PY

echo "[deploy-contract] staging env example placeholders"
python3 - <<'PY'
from pathlib import Path
import re
text = Path(".env.staging.example").read_text()
assert "HELIOS_ENVIRONMENT=staging" in text
assert "HELIOS_E2E_TEST_MODE=false" in text
# Allow documented placeholder prefixes (sk_test_xxx) but not long secret-like blobs.
assert not re.search(r"sk_(?:test|live)_[A-Za-z0-9]{20,}", text)
assert not re.search(r"hel_proj_[A-Za-z0-9]{8,}_[A-Za-z0-9+/=_-]{8,}", text)
assert not re.search(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.", text)
print(".env.staging.example OK")
PY

echo "[deploy-contract] backend config-only check (staging-shaped placeholders)"
BACKEND_PY="${BACKEND_VENV:-$ROOT/backend/.venv}/bin/python"
(
  cd backend
  HELIOS_ENVIRONMENT=staging \
  HELIOS_E2E_TEST_MODE=false \
  HELIOS_ANALYST_NARRATIVE_ENABLED=false \
  HELIOS_ANALYST_ALLOW_THIRD_PARTY=false \
  DATABASE_URL='postgresql://helios_staging:placeholder@db.example/helios_staging' \
  CORS_ORIGINS='https://helios-staging.example.vercel.app' \
  WORKOS_CLIENT_ID='client_staging_example' \
  WORKOS_ISSUER='https://api.workos.com/user_management/client_staging_example' \
  WORKOS_JWKS_URL='https://api.workos.com/sso/jwks/client_staging_example' \
  "$BACKEND_PY" -m app.cli.deployment_check --config-only
)

echo "[deploy-contract] frontend staging-shaped build + bundle scan"
VITE_API_BASE_URL='https://helios-api-staging.example.onrender.com' \
VITE_HELIOS_DEMO_MODE=false \
VITE_HELIOS_ENVIRONMENT=staging \
VITE_HELIOS_E2E_TEST_MODE=false \
  bun run build
bash scripts/scan-browser-bundle.sh

echo "[deploy-contract] OK"
