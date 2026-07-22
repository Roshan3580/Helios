#!/usr/bin/env bash
# Real local Helios backend integration for the TypeScript SDK.
#
# Uses the isolated test PostgreSQL and a locally started FastAPI backend —
# never WorkOS, OpenAI, or any hosted system. The SDK is exercised as the
# PACKED artifact installed into a temp Node fixture, proving real OTLP/HTTP
# protobuf interoperability end to end.
set -euo pipefail

SDK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT="$(cd "$SDK_DIR/../.." && pwd)"
cd "$SDK_DIR"

log() { printf '[ts-sdk-integration] %s\n' "$*"; }
fail() { printf '[ts-sdk-integration] ERROR: %s\n' "$*" >&2; exit 1; }

DB_URL="${HELIOS_TEST_DATABASE_URL:-postgresql://helios_test:helios_test@localhost:5434/helios_test}"
[[ "$DB_URL" == *test* ]] || fail "refusing non-test database URL"

BACKEND_VENV="${BACKEND_VENV:-$ROOT/backend/.venv}"
PYTHON="$BACKEND_VENV/bin/python"
[[ -x "$PYTHON" ]] || fail "backend venv python not found at $PYTHON"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/helios-ts-int.XXXXXX")"
BACKEND_PID=""
cleanup() {
  local code=$?
  set +e
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null
  wait "$BACKEND_PID" 2>/dev/null
  rm -rf "$WORK_DIR"
  exit "$code"
}
trap cleanup EXIT INT TERM

# --- database + backend -------------------------------------------------------
log "applying migrations to the isolated test database"
(cd "$ROOT/backend" && DATABASE_URL="$DB_URL" "$BACKEND_VENV/bin/alembic" upgrade head >/dev/null)

PORT="$("$PYTHON" - <<'PY'
import socket
s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()
PY
)"
log "starting backend on 127.0.0.1:$PORT"
(cd "$ROOT/backend" && DATABASE_URL="$DB_URL" "$BACKEND_VENV/bin/uvicorn" app.main:app \
  --host 127.0.0.1 --port "$PORT" >"$WORK_DIR/uvicorn.log" 2>&1) &
BACKEND_PID=$!
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then break; fi
  sleep 0.5
done
curl -sf "http://127.0.0.1:$PORT/health" >/dev/null || fail "backend did not become healthy"

# --- 1-2. project + scoped key (plus a second project for isolation) ----------
SUFFIX="$RANDOM$RANDOM"
KEY_FILE="$WORK_DIR/key.txt"
OTHER_KEY_FILE="$WORK_DIR/other-key.txt"
log "creating projects and scoped API keys"
CREATED_JSON="$("$PYTHON" "$SDK_DIR/scripts/backend_bootstrap.py" create \
  --database-url "$DB_URL" --backend-dir "$ROOT/backend" \
  --slug "ts-int-$SUFFIX" --key-file "$KEY_FILE")"
"$PYTHON" "$SDK_DIR/scripts/backend_bootstrap.py" create \
  --database-url "$DB_URL" --backend-dir "$ROOT/backend" \
  --slug "ts-int-other-$SUFFIX" --key-file "$OTHER_KEY_FILE" >/dev/null
KEY_PREFIX="$(node -p "JSON.parse(process.argv[1]).key_prefix" "$CREATED_JSON")"
PROJECT_ID="$(node -p "JSON.parse(process.argv[1]).project_id" "$CREATED_JSON")"
log "project $PROJECT_ID (key prefix $KEY_PREFIX)"

# --- 3-4. packed SDK into a fixture -------------------------------------------
log "building and packing the SDK"
npm run build >/dev/null
TARBALL_NAME="$(npm pack --pack-destination "$WORK_DIR" --silent | tail -1)"
FIXTURE_DIR="$WORK_DIR/fixture"
mkdir -p "$FIXTURE_DIR"
cp "$SDK_DIR/fixtures/backend-integration/run.mjs" "$FIXTURE_DIR/"
(cd "$FIXTURE_DIR" \
  && printf '{ "name": "ts-int-fixture", "private": true, "version": "0.0.0" }' > package.json \
  && npm install --silent --no-fund --no-audit "$WORK_DIR/$TARBALL_NAME" >/dev/null)

# --- 5-9. emit + verify --------------------------------------------------------
log "running emit/verify fixture on node"
HELIOS_API_KEY="$(cat "$KEY_FILE")" \
HELIOS_ENDPOINT="http://127.0.0.1:$PORT" \
HELIOS_EXPECT_PROJECT_ID="$PROJECT_ID" \
HELIOS_OTHER_KEY_FILE="$OTHER_KEY_FILE" \
HELIOS_INTEGRATION_MODE=emit \
  node "$FIXTURE_DIR/run.mjs"

# --- 10. revoke and confirm auth fails safely ----------------------------------
log "revoking the key"
"$PYTHON" "$SDK_DIR/scripts/backend_bootstrap.py" revoke \
  --database-url "$DB_URL" --backend-dir "$ROOT/backend" \
  --slug "ts-int-$SUFFIX" --key-prefix "$KEY_PREFIX" >/dev/null

HELIOS_API_KEY="$(cat "$KEY_FILE")" \
HELIOS_ENDPOINT="http://127.0.0.1:$PORT" \
HELIOS_INTEGRATION_MODE=verify-revoked \
  node "$FIXTURE_DIR/run.mjs"

# The plaintext key must never appear in backend logs.
if grep -q "$(cat "$KEY_FILE")" "$WORK_DIR/uvicorn.log"; then
  fail "plaintext key leaked into backend logs"
fi

# Leave the shared test database as we found it.
log "cleaning up integration projects"
for slug in "ts-int-$SUFFIX" "ts-int-other-$SUFFIX"; do
  "$PYTHON" "$SDK_DIR/scripts/backend_bootstrap.py" cleanup \
    --database-url "$DB_URL" --backend-dir "$ROOT/backend" --slug "$slug" >/dev/null
done

log "OK: TypeScript SDK backend integration passed"
