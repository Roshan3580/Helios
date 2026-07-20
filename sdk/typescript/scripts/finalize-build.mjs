// Post-build step: mark dist/cjs as CommonJS (the package root is
// "type": "module") and sanity-check that both build outputs exist.
import { existsSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

for (const required of [
  "dist/esm/index.js",
  "dist/esm/index.d.ts",
  "dist/cjs/index.js",
  "dist/cjs/index.d.ts",
]) {
  if (!existsSync(join(root, required))) {
    console.error(`build output missing: ${required}`);
    process.exit(1);
  }
}

writeFileSync(
  join(root, "dist/cjs/package.json"),
  JSON.stringify({ type: "commonjs" }, null, 2) + "\n",
);
console.log("build finalized: dist/esm (ESM) + dist/cjs (CommonJS)");
