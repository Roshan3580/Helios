#!/usr/bin/env bash
# Helios staging smoke checks — no credentials embedded.
# Required:
#   HELIOS_STAGING_FRONTEND_URL  (https://…)
#   HELIOS_STAGING_API_URL       (https://…)
# Optional machine checks:
#   HELIOS_STAGING_PROJECT_KEY   (hel_proj_* — never echoed)
set -euo pipefail

FRONTEND_URL="${HELIOS_STAGING_FRONTEND_URL:-}"
API_URL="${HELIOS_STAGING_API_URL:-}"
PROJECT_KEY="${HELIOS_STAGING_PROJECT_KEY:-}"
TIMEOUT="${HELIOS_SMOKE_TIMEOUT_SECONDS:-20}"

fail() { printf 'smoke: FAIL %s\n' "$*" >&2; exit 1; }
ok() { printf 'smoke: OK %s\n' "$*"; }
need() { [[ -n "${1:-}" ]] || fail "$2 is required"; }

need "$FRONTEND_URL" "HELIOS_STAGING_FRONTEND_URL"
need "$API_URL" "HELIOS_STAGING_API_URL"

[[ "$FRONTEND_URL" == https://* ]] || fail "frontend URL must be https"
[[ "$API_URL" == https://* ]] || fail "API URL must be https"
FRONTEND_URL="${FRONTEND_URL%/}"
API_URL="${API_URL%/}"

curl_json() {
  local method="$1" url="$2"; shift 2
  curl -fsS --max-time "$TIMEOUT" -X "$method" "$url" "$@"
}

ok "checking frontend root"
code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" "$FRONTEND_URL/")"
[[ "$code" =~ ^[23] ]] || fail "frontend root returned HTTP $code"

ok "checking /health/live"
live="$(curl_json GET "$API_URL/health/live")"
echo "$live" | grep -q '"status":"ok"' || fail "liveness payload unexpected"

ok "checking /health/ready"
ready="$(curl_json GET "$API_URL/health/ready")"
echo "$ready" | grep -q '"status":"ready"' || fail "readiness payload unexpected"

ok "checking sign-in route responds"
signin_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" \
  -L --max-redirs 0 "$FRONTEND_URL/api/auth/sign-in" || true)"
# Expect redirect to WorkOS or 302/307/200 depending on AuthKit config.
[[ "$signin_code" =~ ^(200|302|303|307|308)$ ]] || fail "sign-in returned HTTP $signin_code"

ok "checking E2E session route is not publicly available"
e2e_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" \
  "$FRONTEND_URL/api/e2e/session" || true)"
[[ "$e2e_code" == "404" || "$e2e_code" == "403" || "$e2e_code" == "401" ]] \
  || fail "E2E session route unexpectedly returned HTTP $e2e_code"

ok "checking hostile CORS origin is not reflected"
cors_hdr="$(curl -sS -D - -o /dev/null --max-time "$TIMEOUT" \
  -H "Origin: https://evil.example" \
  "$API_URL/health/live" | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')"
[[ "$cors_hdr" != "https://evil.example" ]] || fail "hostile origin was reflected"

if [[ -n "$PROJECT_KEY" ]]; then
  ok "optional machine read with project key (key not printed)"
  # Intentionally do not echo PROJECT_KEY.
  read_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time "$TIMEOUT" \
    -H "Authorization: Bearer ${PROJECT_KEY}" \
    "$API_URL/v2/traces?limit=1" || true)"
  [[ "$read_code" == "200" ]] || fail "machine trace read returned HTTP $read_code"
  ok "machine trace read succeeded"
else
  ok "skipping optional machine checks (HELIOS_STAGING_PROJECT_KEY unset)"
fi

cat <<'EOF'
smoke: MANUAL browser checklist (WorkOS staging — not automated here)
  1. Open the staging frontend and sign in via AuthKit
  2. Create a project if none exist
  3. Create a scoped project API key; copy once; dismiss reveal
  4. Confirm Dashboard / Traces / Insights load for the selected project
  5. Run Analyze trace / Analyze project with narrative disabled
  6. Sign out and confirm protected /app routes redirect to sign-in
EOF

ok "unauthenticated staging smoke completed"
