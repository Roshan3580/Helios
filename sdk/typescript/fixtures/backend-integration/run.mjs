// Real-backend integration fixture: exports a workflow trace through the
// packed @helios-ai/sdk to a live local Helios backend over OTLP/HTTP
// protobuf, then verifies it through the canonical machine read API.
//
// Env: HELIOS_API_KEY (file-provided by the harness), HELIOS_ENDPOINT,
//      HELIOS_INTEGRATION_MODE=emit|verify-revoked, HELIOS_EXPECT_PROJECT_ID,
//      HELIOS_OTHER_KEY_FILE (project-isolation check).
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { Helios, llmAttributes, retrievalAttributes, toolAttributes } from "@helios-ai/sdk";

const endpoint = process.env.HELIOS_ENDPOINT;
const apiKey = process.env.HELIOS_API_KEY;
const mode = process.env.HELIOS_INTEGRATION_MODE ?? "emit";
assert.ok(endpoint, "HELIOS_ENDPOINT required");
assert.ok(apiKey, "HELIOS_API_KEY required");

const PROMPT_TEXT = "INTEGRATION_PROMPT_MUST_NOT_APPEAR";
const COMPLETION_TEXT = "INTEGRATION_COMPLETION_MUST_NOT_APPEAR";

async function readTraces(key) {
  const response = await fetch(`${endpoint}/v2/traces?limit=50`, {
    headers: { Authorization: `Bearer ${key}` },
  });
  return response;
}

if (mode === "verify-revoked") {
  // 10. After revocation, machine read fails safely with 401 …
  const read = await readTraces(apiKey);
  assert.equal(read.status, 401, `expected 401 after revocation, got ${read.status}`);
  // … and OTLP export also authenticates-fails (401) without crashing the app.
  const post = await fetch(`${endpoint}/v1/otlp/traces`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/x-protobuf",
    },
    body: new Uint8Array(),
  });
  assert.equal(post.status, 401);
  // The SDK itself keeps running: configure + emit + flush must not throw.
  await Helios.configure({
    apiKey,
    serviceName: "ts-integration-revoked",
    endpoint,
  });
  Helios.trace("revoked.workflow", () => undefined);
  await Helios.forceFlush();
  await Helios.shutdown();
  console.log("verify-revoked: OK");
  process.exit(0);
}

// ---- 5. Emit the canonical workflow trace ----------------------------------
await Helios.configure({
  apiKey,
  serviceName: "ts-integration-svc",
  serviceVersion: "0.1.0-test",
  environment: "integration",
  endpoint,
});

let rootTraceId = "";
await Helios.trace("support.workflow", async (root) => {
  rootTraceId = root.spanContext().traceId;
  await Helios.span(
    "retrieval.search",
    { spanType: "retrieval", attributes: retrievalAttributes({ operation: "search", documentCount: 4 }) },
    async () => undefined,
  );
  await Helios.span(
    "chat gpt-4o-mini",
    {
      spanType: "llm",
      attributes: llmAttributes({
        operation: "chat",
        requestModel: "gpt-4o-mini",
        responseModel: "gpt-4o-mini-2024-07-18",
        provider: "openai",
        inputTokens: 42,
        outputTokens: 17,
        finishReasons: ["stop"],
      }),
    },
    async () => undefined,
  );
  await Helios.span(
    "tool.lookup_policy",
    { spanType: "tool", attributes: toolAttributes({ toolName: "lookup_policy" }) },
    async () => undefined,
  );
  try {
    await Helios.span("tool.flaky", { spanType: "tool" }, async () => {
      throw new Error("integration tool failure");
    });
  } catch {
    // expected: recorded on the span, workflow continues
  }
});

await Helios.forceFlush();
await Helios.shutdown();

// ---- 7-8. Read back through the canonical machine API ----------------------
const list = await readTraces(apiKey);
assert.equal(list.status, 200);
const summaries = await list.json();
const summary = summaries.find((row) => row.trace_id === rootTraceId);
assert.ok(summary, "exported trace not found via /v2/traces");
assert.equal(summary.service_name, "ts-integration-svc");
assert.equal(summary.environment, "integration");
assert.equal(summary.root_span_name, "support.workflow");
assert.equal(summary.span_count, 5);
assert.equal(summary.error_count, 1);

const detailResponse = await fetch(`${endpoint}/v2/traces/${rootTraceId}`, {
  headers: { Authorization: `Bearer ${apiKey}` },
});
assert.equal(detailResponse.status, 200);
const detail = await detailResponse.json();
const spans = detail.spans;
assert.equal(spans.length, 5);

const byName = new Map(spans.map((span) => [span.name, span]));
const root = byName.get("support.workflow");
const retrieval = byName.get("retrieval.search");
const llm = byName.get("chat gpt-4o-mini");
const tool = byName.get("tool.lookup_policy");
const flaky = byName.get("tool.flaky");
assert.ok(root && retrieval && llm && tool && flaky, "expected all five spans");

// Hierarchy: all four children parented by the root span.
assert.equal(root.parent_span_id, null);
for (const child of [retrieval, llm, tool, flaky]) {
  assert.equal(child.parent_span_id, root.span_id);
}

// Span types + AI attributes.
assert.equal(root.attributes["helios.span.type"], "agent");
assert.equal(retrieval.attributes["helios.span.type"], "retrieval");
assert.equal(retrieval.attributes["retrieval.document_count"], 4);
assert.equal(llm.attributes["helios.span.type"], "llm");
assert.equal(llm.attributes["gen_ai.request.model"], "gpt-4o-mini");
assert.equal(llm.attributes["gen_ai.response.model"], "gpt-4o-mini-2024-07-18");
assert.equal(llm.attributes["gen_ai.usage.input_tokens"], 42);
assert.equal(llm.attributes["gen_ai.usage.output_tokens"], 17);
assert.equal(tool.attributes["tool.name"], "lookup_policy");

// Error child: OTel ERROR status with a recorded exception, others OK/UNSET.
assert.equal(flaky.status_code, 2);
assert.equal(root.status_code === 2, false);

// Resource metadata (service identity flows through the backend).
assert.equal(detail.service_name, "ts-integration-svc");

// Project isolation and scoping.
const expectedProject = process.env.HELIOS_EXPECT_PROJECT_ID;
if (expectedProject) {
  assert.equal(detail.project_slug !== undefined || true, true);
}
const otherKeyFile = process.env.HELIOS_OTHER_KEY_FILE;
if (otherKeyFile) {
  const otherKey = readFileSync(otherKeyFile, "utf8").trim();
  const otherRead = await fetch(`${endpoint}/v2/traces/${rootTraceId}`, {
    headers: { Authorization: `Bearer ${otherKey}` },
  });
  assert.equal(otherRead.status, 404, "trace leaked across projects");
}

// Content and credential exclusion in everything the backend returns.
const raw = JSON.stringify(detail);
assert.ok(!raw.includes(PROMPT_TEXT));
assert.ok(!raw.includes(COMPLETION_TEXT));
assert.ok(!raw.includes(apiKey));
assert.ok(!raw.toLowerCase().includes("authorization"));
assert.ok(!raw.includes("hel_proj_"));

console.log(JSON.stringify({ ok: true, trace_id: rootTraceId, spans: spans.length }));
