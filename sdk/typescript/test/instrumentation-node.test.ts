/**
 * Optional Node auto-instrumentation bundle against a local HTTP server only.
 * Own process so http patching state cannot leak into other test files.
 */

import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";

import { Helios } from "../src/runtime.js";
import { LocalCollector } from "./helpers/collector.js";
import { FakeOpenAiServer } from "./helpers/fake-openai.js";
import { TEST_API_KEY, resetRuntime } from "./helpers/reset.js";

let collector: LocalCollector;
let localServer: FakeOpenAiServer;

before(async () => {
  await resetRuntime();
  collector = await LocalCollector.start();
  localServer = await FakeOpenAiServer.start();
  await Helios.configure({
    apiKey: TEST_API_KEY,
    serviceName: "node-instr-svc",
    endpoint: collector.endpoint,
    instrumentations: { node: true },
  });
});

after(async () => {
  await resetRuntime();
  await collector.stop();
  await localServer.stop();
});

describe("Node auto-instrumentation (enabled)", () => {
  it("traces local outgoing http requests", async () => {
    // Resolve http AFTER configure() so the wrapped export is used (the same
    // import-order rule documented for applications).
    const { get: httpGet } = await import("node:http");
    await new Promise<void>((resolve, reject) => {
      httpGet(`${localServer.baseUrl.replace(/\/v1$/, "")}/v1/ping`, (res) => {
        res.resume();
        res.on("end", resolve);
      }).on("error", reject);
    });
    await Helios.forceFlush();
    const body = collector.allBodies();
    // instrumentation-http 0.220.x emits the legacy HTTP semconv by default
    // (`http.method`); accept the stable key too for forward compatibility.
    assert.ok(
      body.includes(Buffer.from("http.method")) ||
        body.includes(Buffer.from("http.request.method")),
      "expected an HTTP client span",
    );
    assert.ok(body.includes(Buffer.from("/v1/ping")));
  });

  it("never traces its own OTLP exporter requests (no self-trace loop)", async () => {
    // If http client instrumentation wrapped the exporter's POSTs, each
    // request would carry an injected `traceparent` header (and every flush
    // would spawn a new span for the previous flush — an infinite loop).
    // Note: the in-process test collector's *server* side legitimately gets
    // instrumented; the client-side suppression is what matters here.
    await Helios.forceFlush();
    await new Promise((resolve) => setTimeout(resolve, 100));
    await Helios.forceFlush();
    assert.ok(collector.requests.length > 0);
    for (const request of collector.requests) {
      assert.equal(request.headers["traceparent"], undefined);
    }
  });
});
