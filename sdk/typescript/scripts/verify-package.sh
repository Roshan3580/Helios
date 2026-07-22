#!/usr/bin/env bash
# Package-artifact verification for @helios-ai/sdk:
#   1. npm pack (deterministic tarball from the committed allowlist)
#   2. packed-file allowlist + secret scan of the artifact
#   3. install the tarball into temp fixtures and run ESM / CJS / TypeScript
#      consumer smokes on plain Node (no bun, no repository internals).
set -euo pipefail

SDK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SDK_DIR"

log() { printf '[verify-package] %s\n' "$*"; }
fail() { printf '[verify-package] ERROR: %s\n' "$*" >&2; exit 1; }

[[ -f dist/esm/index.js ]] || fail "dist missing; run npm run build first"

WORK_DIR="$(mktemp -d "${TMPDIR:-/tmp}/helios-ts-sdk.XXXXXX")"
trap 'rm -rf "$WORK_DIR"' EXIT

# --- 1. pack -----------------------------------------------------------------
log "packing"
TARBALL_NAME="$(npm pack --pack-destination "$WORK_DIR" --silent | tail -1)"
TARBALL="$WORK_DIR/$TARBALL_NAME"
[[ -f "$TARBALL" ]] || fail "npm pack produced no tarball"
log "tarball: $TARBALL_NAME"

# --- 2. content allowlist ----------------------------------------------------
log "checking packed file allowlist"
tar -tzf "$TARBALL" | sed 's#^package/##' | sort > "$WORK_DIR/files.txt"
BAD_FILES="$(grep -Ev '^(package\.json|README\.md|dist/)' "$WORK_DIR/files.txt" || true)"
[[ -z "$BAD_FILES" ]] || fail "unexpected files in package: $BAD_FILES"
for required in package.json README.md dist/esm/index.js dist/esm/index.d.ts \
  dist/cjs/index.js dist/cjs/index.d.ts dist/cjs/package.json; do
  grep -qx "$required" "$WORK_DIR/files.txt" || fail "missing packed file: $required"
done
if grep -E '(^|/)(test|tests|fixtures|node_modules|scripts|src)/' "$WORK_DIR/files.txt"; then
  fail "repository internals leaked into the package"
fi

# --- secret scan of the packed artifact --------------------------------------
log "scanning packed artifact for secrets"
EXTRACT_DIR="$WORK_DIR/extracted"
mkdir -p "$EXTRACT_DIR"
tar -xzf "$TARBALL" -C "$EXTRACT_DIR"
# Real Helios keys are hel_proj_<16 hex>_<43+ chars>. Docs placeholders are fine.
if grep -rE 'hel_proj_[0-9a-f]{16}_[A-Za-z0-9_-]{30,}' "$EXTRACT_DIR" >/dev/null; then
  fail "generated-looking Helios key found in package"
fi
if grep -rE 'sk-(proj-)?[A-Za-z0-9]{20,}' "$EXTRACT_DIR" >/dev/null; then
  fail "OpenAI-style key found in package"
fi
if grep -rE 'eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}' "$EXTRACT_DIR" >/dev/null; then
  fail "JWT-like token found in package"
fi
if grep -r "Authorization: Bearer hel_proj_[0-9a-f]" "$EXTRACT_DIR" >/dev/null; then
  fail "authorization header with generated key found in package"
fi

# --- version consistency ------------------------------------------------------
PKG_VERSION="$(node -p "require('$SDK_DIR/package.json').version")"
DIST_VERSION="$(node -e "const m=require('$EXTRACT_DIR/package/dist/cjs/version.js'); console.log(m.SDK_VERSION)")"
[[ "$PKG_VERSION" == "$DIST_VERSION" ]] || fail "SDK_VERSION ($DIST_VERSION) != package.json version ($PKG_VERSION)"

# --- 3. consumer fixtures ------------------------------------------------------
run_consumer() {
  local name="$1" install_extra="$2"
  local dir="$WORK_DIR/$name"
  mkdir -p "$dir"
  cp -R "$SDK_DIR/fixtures/$name/." "$dir/"
  (
    cd "$dir"
    cat > package.json <<JSON
{ "name": "fixture-$name", "private": true, "version": "0.0.0" }
JSON
    log "installing tarball into $name fixture"
    npm install --silent --no-fund --no-audit "$TARBALL" $install_extra >/dev/null
  )
}

run_consumer consumer-esm ""
log "running ESM consumer on node"
node "$WORK_DIR/consumer-esm/run.mjs"

run_consumer consumer-cjs ""
log "running CJS consumer on node"
node "$WORK_DIR/consumer-cjs/run.cjs"

run_consumer consumer-ts ""
log "compiling TypeScript consumer"
(
  cd "$WORK_DIR/consumer-ts"
  "$SDK_DIR/node_modules/.bin/tsc" -p tsconfig.json --typeRoots "$SDK_DIR/node_modules/@types"
  node out/main.js
)

log "OK: package verified"
