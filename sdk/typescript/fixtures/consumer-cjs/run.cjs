// CommonJS consumer smoke test for the packed @helios-ai/sdk artifact.
"use strict";
const assert = require("node:assert/strict");
const { createServer } = require("node:http");

const { Helios, toolAttributes, HeliosConfigurationError } = require("@helios-ai/sdk");

const KEY = "hel_proj_0123456789abcdef_fixturesecretfixturesecret";

async function main() {
  const requests = [];
  const server = createServer((req, res) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      requests.push({ url: req.url, body: Buffer.concat(chunks) });
      res.statusCode = 200;
      res.end();
    });
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;

  assert.equal(Helios.isConfigured(), false);
  assert.ok(HeliosConfigurationError.prototype instanceof Error);

  await Helios.configure({
    apiKey: KEY,
    serviceName: "cjs-consumer",
    endpoint: `http://127.0.0.1:${port}`,
  });

  Helios.trace("cjs.workflow", () => {
    Helios.span("tool.lookup", { spanType: "tool", attributes: toolAttributes({ toolName: "lookup" }) }, () => undefined);
  });

  await Helios.forceFlush();
  await Helios.shutdown();
  server.close();

  assert.equal(requests.length, 1);
  assert.equal(requests[0].url, "/v1/otlp/traces");
  assert.ok(requests[0].body.includes(Buffer.from("cjs.workflow")));
  assert.ok(requests[0].body.includes(Buffer.from("tool.lookup")));
  console.log("CJS consumer smoke: OK");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
