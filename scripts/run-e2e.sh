#!/usr/bin/env bash
# Helios browser E2E harness — isolated Postgres, loopback JWKS, FastAPI, Vite.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

BACKEND_VENV="${BACKEND_VENV:-$ROOT/backend/.venv}"
PYTHON="${PYTHON:-$BACKEND_VENV/bin/python}"
[[ -x "$PYTHON" ]] || { echo "error: backend venv python not found at $PYTHON" >&2; exit 1; }

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/helios-e2e.XXXXXX")"
JWKS_PID="" BACKEND_PID="" FRONTEND_PID=""
TOKEN_FILE="$TMP_DIR/access.jwt"
PEM_FILE="$TMP_DIR/private.pem"
READY_FILE="$TMP_DIR/jwks.ready"
ORG_B_TOKEN_FILE="$TMP_DIR/access_b.jwt"
ORG_A="org_01E2EORG00000000000000001"
ORG_B="org_01E2EORG00000000000000002"
USER_A="user_01E2EUSER000000000000001"
# The WorkOS application (client) the E2E tokens are minted for; the backend
# verifier validates the token's client_id claim against this exact value.
E2E_CLIENT_ID="client_e2e_helios"

log() { printf '[e2e] %s\n' "$*"; }
fail() { printf '[e2e] ERROR: %s\n' "$*" >&2; exit 1; }

cleanup() {
  local code=$?
  set +e
  [[ -n "${FRONTEND_PID}" ]] && kill "${FRONTEND_PID}" 2>/dev/null
  [[ -n "${BACKEND_PID}" ]] && kill "${BACKEND_PID}" 2>/dev/null
  [[ -n "${JWKS_PID}" ]] && kill "${JWKS_PID}" 2>/dev/null
  wait "${FRONTEND_PID}" "${BACKEND_PID}" "${JWKS_PID}" 2>/dev/null || true
  rm -rf "$TMP_DIR"
  exit "$code"
}
trap cleanup EXIT INT TERM

pick_port() {
  "$PYTHON" - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
}

wait_http() {
  local url="$1" name="$2" attempts="${3:-90}"
  local i
  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$name ready"
      return 0
    fi
    sleep 0.5
  done
  fail "$name did not become ready: $url"
}

log "starting isolated postgres"
docker compose -f docker-compose.test.yml up -d --wait
DATABASE_URL="postgresql://helios_test:helios_test@127.0.0.1:5434/helios_test"

JWKS_PORT="$(pick_port)"
BACKEND_PORT="$(pick_port)"
FRONTEND_PORT="$(pick_port)"
ISSUER="http://127.0.0.1:${JWKS_PORT}/"
JWKS_URL="http://127.0.0.1:${JWKS_PORT}/jwks"

log "starting loopback JWKS on :${JWKS_PORT}"
"$PYTHON" "$ROOT/scripts/e2e/jwks_server.py" \
  --host 127.0.0.1 --port "$JWKS_PORT" --issuer "$ISSUER" \
  --client-id "$E2E_CLIENT_ID" --org-id "$ORG_A" \
  --token-out "$TOKEN_FILE" --pem-out "$PEM_FILE" --ready-file "$READY_FILE" &
JWKS_PID=$!
for ((i=1; i<=60; i++)); do [[ -f "$READY_FILE" ]] && break; sleep 0.1; done
[[ -f "$READY_FILE" && -s "$TOKEN_FILE" && -s "$PEM_FILE" ]] || fail "JWKS bootstrap failed"
wait_http "$JWKS_URL" "JWKS"

"$PYTHON" "$ROOT/scripts/e2e/mint_token.py" \
  --pem-file "$PEM_FILE" --issuer "$ISSUER" --client-id "$E2E_CLIENT_ID" \
  --org-id "$ORG_B" --token-out "$ORG_B_TOKEN_FILE"

log "resetting schema + linking orgs"
"$PYTHON" "$ROOT/scripts/e2e/bootstrap_db.py" \
  --database-url "$DATABASE_URL" --org-a "$ORG_A" --org-b "$ORG_B"

ACCESS_TOKEN="$(cat "$TOKEN_FILE")"

log "starting FastAPI on :${BACKEND_PORT}"
(
  cd "$ROOT/backend"
  export DATABASE_URL WORKOS_CLIENT_ID="$E2E_CLIENT_ID"
  export WORKOS_ISSUER="$ISSUER" WORKOS_JWKS_URL="$JWKS_URL"
  export HELIOS_E2E_TEST_MODE=true
  export HELIOS_ENVIRONMENT=e2e
  export HELIOS_ANALYST_NARRATIVE_ENABLED=false HELIOS_ANALYST_ALLOW_THIRD_PARTY=false
  export OPENAI_API_KEY="" HELIOS_DEMO_MODE=false
  export CORS_ORIGINS="http://127.0.0.1:${FRONTEND_PORT},http://localhost:${FRONTEND_PORT}"
  exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$BACKEND_PORT"
) >"$TMP_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
wait_http "http://127.0.0.1:${BACKEND_PORT}/health/live" "backend"
log "starting Vite on :${FRONTEND_PORT}"
(
  export VITE_API_BASE_URL="http://127.0.0.1:${BACKEND_PORT}"
  export VITE_HELIOS_DEMO_MODE=false VITE_HELIOS_E2E_TEST_MODE=true
  export HELIOS_E2E_TEST_MODE=true
  export HELIOS_E2E_ACCESS_TOKEN="$ACCESS_TOKEN"
  export HELIOS_E2E_ORG_ID="$ORG_A" HELIOS_E2E_USER_ID="$USER_A"
  export HELIOS_E2E_USER_EMAIL="e2e@helios.test"
  export HELIOS_E2E_JWKS_URL="$JWKS_URL" HELIOS_E2E_ISSUER="$ISSUER"
  export WORKOS_JWKS_URL="$JWKS_URL" WORKOS_ISSUER="$ISSUER"
  export NODE_ENV=development
  exec bun run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT" --strictPort
) >"$TMP_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
wait_http "http://127.0.0.1:${FRONTEND_PORT}/" "frontend" 120

export HELIOS_E2E_BASE_URL="http://127.0.0.1:${FRONTEND_PORT}"
export HELIOS_E2E_API_URL="http://127.0.0.1:${BACKEND_PORT}"
export HELIOS_E2E_ACCESS_TOKEN_FILE="$TOKEN_FILE"
export HELIOS_E2E_ORG_B_TOKEN_FILE="$ORG_B_TOKEN_FILE"
export HELIOS_E2E_ORG_A="$ORG_A" HELIOS_E2E_ORG_B="$ORG_B"
export HELIOS_E2E_ISSUER="$ISSUER" HELIOS_E2E_JWKS_URL="$JWKS_URL"

log "running Playwright"
set +e
if [[ "${1:-}" == "--headed" ]]; then
  shift
  bunx playwright test --headed "$@"
else
  bunx playwright test "$@"
fi
status=$?
set -e
exit "$status"