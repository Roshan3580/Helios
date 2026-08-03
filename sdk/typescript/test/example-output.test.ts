import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, it } from "node:test";

const repoRoot = existsSync(resolve(process.cwd(), "examples"))
  ? process.cwd()
  : resolve(process.cwd(), "../..");
const EXAMPLES = [
  resolve(repoRoot, "examples/typescript-basic/main.mjs"),
  resolve(repoRoot, "examples/typescript-openai/main.cjs"),
];

describe("official example export output", () => {
  for (const path of EXAMPLES) {
    it(`${path.split("/").at(-2)} uses neutral, diagnosable export wording`, () => {
      const source = readFileSync(path, "utf8");
      assert.match(source, /diagnostics:\s*"warn"/);
      assert.match(source, /Export completed locally\. Check Helios to confirm trace arrival/);
      assert.match(source, /exporter errors are authoritative/i);
      assert.doesNotMatch(source, /trace (?:exported|submitted|sent)/i);
      assert.doesNotMatch(source, /export (?:succeeded|successful)/i);
    });
  }
});
