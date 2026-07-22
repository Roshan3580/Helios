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
import re
from pathlib import Path

CONFIG_CMD = "python -m app.cli.deployment_check --config-only"
MIGRATE_CMD = "alembic upgrade head"
START_CMD = "uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1"


def check_ordering(pre_deploy: str) -> None:
    """Fail-closed contract shared by the PyYAML and stdlib-fallback paths.

    Both paths must reject the same defects: config validation running
    after (or missing from) the migration step, `;` instead of `&&`
    (which drops fail-fast semantics), and any downgrade command.
    """
    config_idx = pre_deploy.find(CONFIG_CMD)
    migrate_idx = pre_deploy.find(MIGRATE_CMD)
    assert config_idx != -1, "preDeployCommand missing config-only validation"
    assert migrate_idx != -1, "preDeployCommand missing alembic upgrade head"
    assert config_idx < migrate_idx, "config validation must run before migration"
    connector = pre_deploy[config_idx:migrate_idx]
    assert "&&" in connector, "config validation and migration must be fail-fast (&&)"
    assert ";" not in connector, "commands must not be joined with ';'"
    assert "downgrade" not in pre_deploy, "no downgrade command allowed in preDeployCommand"


def check_valid_fixture() -> None:
    check_ordering(f"{CONFIG_CMD} && {MIGRATE_CMD}")

    def must_fail(pre_deploy: str, label: str) -> None:
        try:
            check_ordering(pre_deploy)
        except AssertionError:
            return
        raise AssertionError(f"expected failure for case: {label}")

    must_fail(f"{MIGRATE_CMD} && {CONFIG_CMD}", "config runs after migration")
    must_fail(MIGRATE_CMD, "missing config-only validation entirely")
    must_fail(CONFIG_CMD, "missing migration command entirely")
    must_fail(f"{CONFIG_CMD} ; {MIGRATE_CMD}", "';' instead of '&&' loses fail-fast behavior")
    must_fail(f"{CONFIG_CMD} && alembic downgrade base && {MIGRATE_CMD}", "downgrade command present")


check_valid_fixture()

text = Path("render.yaml").read_text()

try:
    import yaml
except ImportError:
    yaml = None

if yaml is not None:
    data = yaml.safe_load(text)
    service = data["services"][0]
    assert service["name"] == "helios-api-staging"
    assert service["rootDir"] == "backend"
    assert service["healthCheckPath"] == "/health/ready"
    assert service["startCommand"] == START_CMD
    pre_deploy = service["preDeployCommand"]
    mode = "PyYAML"
else:
    assert "helios-api-staging" in text
    assert "rootDir: backend" in text
    assert "healthCheckPath: /health/ready" in text
    assert f"startCommand: {START_CMD}" in text
    match = re.search(r"preDeployCommand:\s*(.+)", text)
    assert match, "preDeployCommand not found in render.yaml"
    pre_deploy = match.group(1).strip()
    mode = "stdlib fallback; PyYAML unavailable"

check_ordering(pre_deploy)

assert "HELIOS_E2E_TEST_MODE" in text
assert "sk_test" not in text and "sk_live" not in text
assert "hel_proj_" not in text

assert re.search(r'HELIOS_DEMO_MODE\s*\n\s*value:\s*"false"', text), \
    "staging HELIOS_DEMO_MODE must default to false"
assert re.search(r'HELIOS_E2E_TEST_MODE\s*\n\s*value:\s*"false"', text), \
    "staging HELIOS_E2E_TEST_MODE must default to false"
assert re.search(r'HELIOS_ANALYST_NARRATIVE_ENABLED\s*\n\s*value:\s*"false"', text), \
    "staging HELIOS_ANALYST_NARRATIVE_ENABLED must default to false"

for secret_key in ("CORS_ORIGINS", "WORKOS_CLIENT_ID", "WORKOS_ISSUER", "WORKOS_JWKS_URL"):
    assert re.search(rf"{secret_key}\s*\n\s*sync:\s*false", text), \
        f"{secret_key} must remain dashboard-managed (sync: false)"

print(f"render.yaml structural OK ({mode})")
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
  HELIOS_DEMO_MODE=false \
  HELIOS_ANALYST_NARRATIVE_ENABLED=false \
  HELIOS_ANALYST_ALLOW_THIRD_PARTY=false \
  DATABASE_URL='postgresql://helios_staging:placeholder@db.example/helios_staging' \
  CORS_ORIGINS='https://helios-staging.example.vercel.app' \
  WORKOS_CLIENT_ID='client_staging_example' \
  WORKOS_ISSUER='https://api.workos.com/user_management/client_staging_example' \
  WORKOS_JWKS_URL='https://api.workos.com/sso/jwks/client_staging_example' \
  "$BACKEND_PY" -m app.cli.deployment_check --config-only
)

echo "[deploy-contract] staging + HELIOS_DEMO_MODE=true must fail (L1 regression guard)"
(
  cd backend
  if HELIOS_ENVIRONMENT=staging \
    HELIOS_E2E_TEST_MODE=false \
    HELIOS_DEMO_MODE=true \
    HELIOS_ANALYST_NARRATIVE_ENABLED=false \
    HELIOS_ANALYST_ALLOW_THIRD_PARTY=false \
    DATABASE_URL='postgresql://helios_staging:placeholder@db.example/helios_staging' \
    CORS_ORIGINS='https://helios-staging.example.vercel.app' \
    WORKOS_CLIENT_ID='client_staging_example' \
    WORKOS_ISSUER='https://api.workos.com/user_management/client_staging_example' \
    WORKOS_JWKS_URL='https://api.workos.com/sso/jwks/client_staging_example' \
    "$BACKEND_PY" -m app.cli.deployment_check --config-only >/dev/null 2>&1; then
    echo "expected HELIOS_DEMO_MODE=true to fail staging config check" >&2
    exit 1
  fi
)

echo "[deploy-contract] unknown environment must fail config check"
(
  if HELIOS_ENVIRONMENT='prod' \
    HELIOS_E2E_TEST_MODE=false \
    HELIOS_DEMO_MODE=false \
    DATABASE_URL='postgresql://u:p@db.example/helios_staging' \
    CORS_ORIGINS='https://helios-staging.example.onrender.com' \
    WORKOS_CLIENT_ID='client_staging_example' \
    WORKOS_ISSUER='https://api.workos.com/user_management/client_staging_example' \
    WORKOS_JWKS_URL='https://api.workos.com/sso/jwks/client_staging_example' \
    "$BACKEND_PY" -m app.cli.deployment_check --config-only >/dev/null 2>&1; then
    echo "expected unknown HELIOS_ENVIRONMENT=prod to fail config check" >&2
    exit 1
  fi
)

echo "[deploy-contract] render.yaml preDeployCommand includes config validation"
if ! grep -q "deployment_check --config-only && alembic upgrade head" render.yaml; then
  echo "expected render.yaml preDeployCommand to run config check before alembic" >&2
  exit 1
fi

echo "[deploy-contract] frontend staging-shaped build + bundle scan"
VITE_API_BASE_URL='https://helios-api-staging.example.onrender.com' \
VITE_HELIOS_DEMO_MODE=false \
VITE_HELIOS_ENVIRONMENT=staging \
VITE_HELIOS_E2E_TEST_MODE=false \
  bun run build
bash scripts/scan-browser-bundle.sh

echo "[deploy-contract] OK"
