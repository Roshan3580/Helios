// ESM consumer smoke test for the packed @helios-ai/sdk artifact.
// Exports a real trace to a local in-process collector; no external network.
import assert from "node:assert/strict";
import { createServer } from "node:http";

import { Helios, llmAttributes, SPAN_TYPES, SDK_VERSION } from "@helios-ai/sdk";

const requests = [];
const server = createServer((req, res) => {
  const chunks = [];
  req.on("data", (chunk) => chunks.push(chunk));
  req.on("end", () => {
    requests.push({ url: req.url, auth: req.headers.authorization, body: Buffer.concat(chunks) });
    res.statusCode = 200;
    res.end();
  });
});
await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
const port = server.address().port;

const KEY = "hel_proj_0123456789abcdef_fixturesecretfixturesecret";

// Importing must not configure anything.
assert.equal(Helios.isConfigured(), false);
assert.equal(typeof SDK_VERSION, "string");
assert.equal(SPAN_TYPES.llm, "llm");

await Helios.configure({
  apiKey: KEY,
  serviceName: "esm-consumer",
  endpoint: `http://127.0.0.1:${port}`,
  environment: "test",
});
assert.equal(Helios.isConfigured(), true);

const result = await Helios.trace("consumer.workflow", async () => {
  return Helios.span(
    "chat fixture-model",
    { spanType: "llm", attributes: llmAttributes({ requestModel: "fixture-model", inputTokens: 3 }) },
    () => "done",
  );
});
assert.equal(result, "done");

await Helios.forceFlush();
await Helios.shutdown();
server.close();

assert.equal(requests.length, 1);
assert.equal(requests[0].url, "/v1/otlp/traces");
assert.equal(requests[0].auth, `Bearer ${KEY}`);
assert.ok(requests[0].body.includes(Buffer.from("consumer.workflow")));
assert.ok(requests[0].body.includes(Buffer.from("fixture-model")));
console.log("ESM consumer smoke: OK");
