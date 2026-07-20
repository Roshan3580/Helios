import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";

import { Helios } from "../src/runtime.js";
import { LocalCollector } from "./helpers/collector.js";
import { TEST_API_KEY, resetRuntime } from "./helpers/reset.js";

let collector: LocalCollector;

beforeEach(async () => {
  await resetRuntime();
  collector = await LocalCollector.start();
});

afterEach(async () => {
  await resetRuntime();
  await collector.stop();
});

describe("OTLP export", () => {
  it("posts protobuf to the canonical route with a bearer header", async () => {
    await Helios.configure({
      apiKey: TEST_API_KEY,
      serviceName: "export-svc",
      environment: "development",
      endpoint: collector.endpoint,
    });
    Helios.trace("wf.export", () => undefined);
    await Helios.forceFlush();

    assert.equal(collector.requests.length, 1);
    const request = collector.requests[0]!;
    assert.equal(request.method, "POST");
    assert.equal(request.url, "/v1/otlp/traces");
    assert.equal(request.headers["content-type"], "application/x-protobuf");
    assert.equal(request.headers["authorization"], `Bearer ${TEST_API_KEY}`);
    // Credentials belong in the header, never the URL.
    assert.ok(!request.url.includes(TEST_API_KEY));

    const body = request.body;
    assert.ok(body.includes(Buffer.from("wf.export")));
    assert.ok(body.includes(Buffer.from("export-svc")));
    assert.ok(body.includes(Buffer.from("deployment.environment.name")));
    assert.ok(body.includes(Buffer.from("development")));
    assert.ok(body.includes(Buffer.from("helios.sdk.name")));
    assert.ok(body.includes(Buffer.from("telemetry.sdk.language")));
    // The API key must never appear in the export payload.
    assert.ok(!body.includes(Buffer.from(TEST_API_KEY)));
  });

  it("accepts a full ingest URL without double-appending the path", async () => {
    await Helios.configure({
      apiKey: TEST_API_KEY,
      serviceName: "export-svc",
      endpoint: `${collector.endpoint}/v1/otlp/traces`,
    });
    Helios.trace("wf.full-url", () => undefined);
    await Helios.forceFlush();
    assert.equal(collector.requests[0]?.url, "/v1/otlp/traces");
  });

  it("includes service.version and custom resource attributes", async () => {
    await Helios.configure({
      apiKey: TEST_API_KEY,
      serviceName: "export-svc",
      serviceVersion: "3.1.4",
      endpoint: collector.endpoint,
      resourceAttributes: { "team.name": "support" },
    });
    Helios.trace("wf.resource", () => undefined);
    await Helios.forceFlush();
    const body = collector.allBodies();
    assert.ok(body.includes(Buffer.from("service.version")));
    assert.ok(body.includes(Buffer.from("3.1.4")));
    assert.ok(body.includes(Buffer.from("team.name")));
  });

  it("survives exporter failures without crashing the application", async () => {
    await Helios.configure({
      apiKey: TEST_API_KEY,
      serviceName: "export-svc",
      endpoint: collector.endpoint,
      timeoutMillis: 2000,
    });
    collector.responseStatus = 500;

    const unhandled: unknown[] = [];
    const onUnhandled = (reason: unknown) => unhandled.push(reason);
    process.on("unhandledRejection", onUnhandled);
    try {
      Helios.trace("wf.failing-export", () => undefined);
      // forceFlush absorbs routine export failures instead of throwing them
      // into application code.
      await Helios.forceFlush();
      assert.equal(
        Helios.span("still-works", () => "ok"),
        "ok",
      );
      // shutdown is also safe while the collector keeps failing.
      await Helios.shutdown();
      await new Promise((resolve) => setTimeout(resolve, 50));
      assert.deepEqual(unhandled, []);
    } finally {
      process.off("unhandledRejection", onUnhandled);
    }
  });

  it("flushes on shutdown", async () => {
    await Helios.configure({
      apiKey: TEST_API_KEY,
      serviceName: "export-svc",
      endpoint: collector.endpoint,
    });
    Helios.trace("wf.shutdown", () => undefined);
    await Helios.shutdown();
    assert.ok(collector.bodiesInclude("wf.shutdown"));
  });
});
