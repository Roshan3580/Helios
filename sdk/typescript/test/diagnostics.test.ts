import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { createRedactingDiagLogger, redactDiagnosticText } from "../src/diagnostics.js";

describe("diagnostic redaction", () => {
  it("redacts project API keys", () => {
    const text = redactDiagnosticText(
      "export failed for key hel_proj_0123abcd_secretsecretsecret at endpoint",
    );
    assert.ok(!text.includes("secretsecretsecret"));
    assert.ok(text.includes("hel_proj_[REDACTED]"));
  });

  it("redacts bearer headers", () => {
    const text = redactDiagnosticText(
      'request headers {"Authorization":"Bearer hel_proj_abc_def"}',
    );
    assert.ok(!text.includes("hel_proj_abc_def"));
    assert.ok(text.includes("Bearer [REDACTED]") || text.includes("hel_proj_[REDACTED]"));
  });

  it("redacts provider-key-shaped strings and JWTs", () => {
    assert.ok(!redactDiagnosticText("using sk-abcdef1234567890").includes("sk-abcdef1234567890"));
    const jwt = `eyJ${"a".repeat(12)}.${"b".repeat(12)}.${"c".repeat(12)}`;
    assert.ok(!redactDiagnosticText(`token ${jwt}`).includes(jwt));
  });

  it("logger redacts every argument, including errors and objects", () => {
    const lines: string[] = [];
    const fake = {
      error: (...args: unknown[]) => lines.push(args.join(" ")),
      warn: (...args: unknown[]) => lines.push(args.join(" ")),
      info: (...args: unknown[]) => lines.push(args.join(" ")),
      debug: (...args: unknown[]) => lines.push(args.join(" ")),
    };
    const logger = createRedactingDiagLogger(fake);
    logger.error("failed", new Error("auth Bearer hel_proj_leak_leak failed"));
    logger.warn("headers", { Authorization: "Bearer hel_proj_leak_leak" });
    const output = lines.join("\n");
    assert.ok(!output.includes("hel_proj_leak_leak"));
    assert.ok(output.includes("[helios-sdk]"));
  });
});
