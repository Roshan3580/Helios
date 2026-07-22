#!/usr/bin/env bash
# Scan Nitro/Vercel browser assets for forbidden server-secret leakage.
# Usage: bash scripts/scan-browser-bundle.sh [output-dir]
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="${1:-$ROOT/.vercel/output/static}"

[[ -d "$OUT" ]] || { echo "scan: missing output dir: $OUT" >&2; exit 1; }

# Fail on these identifiers appearing in client static assets.
FORBIDDEN_PATTERNS=(
  'WORKOS_API_KEY'
  'WORKOS_COOKIE_PASSWORD'
  'OPENAI_API_KEY'
  'DATABASE_URL'
  'HELIOS_E2E_ACCESS_TOKEN'
  'postgresql://'
  'postgres://'
)

fail=0
for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
  if rg -l --glob '*.js' --glob '*.mjs' --glob '*.html' -F "$pattern" "$OUT" >/tmp/helios-bundle-hits.$$ 2>/dev/null; then
    echo "scan: FORBIDDEN pattern in browser assets: $pattern" >&2
    cat /tmp/helios-bundle-hits.$$ >&2
    fail=1
  fi
done
rm -f /tmp/helios-bundle-hits.$$

# E2E client flag string may appear only as the boolean env name for guards;
# the ACCESS_TOKEN name must never appear (checked above). Allow HELIOS_E2E_TEST_MODE
# only if accompanied by false-path dead code — still flag the ACCESS token.

# Generated project keys / JWTs (long material, not the hel_proj_ prefix alone).
if rg -l --glob '*.js' --glob '*.mjs' -e 'hel_proj_[A-Za-z0-9]{8,}_[A-Za-z0-9+/=_-]{8,}' "$OUT" >/dev/null 2>&1; then
  echo "scan: FORBIDDEN generated project key material in browser assets" >&2
  fail=1
fi
if rg -l --glob '*.js' --glob '*.mjs' -e 'eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+' "$OUT" >/dev/null 2>&1; then
  echo "scan: FORBIDDEN JWT-like material in browser assets" >&2
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "scan: FAILED" >&2
  exit 1
fi
echo "scan: OK browser assets under $OUT"
