import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { trace as otelTrace } from "@opentelemetry/api";
import { NodeTracerProvider } from "@opentelemetry/sdk-trace-node";

import { Helios } from "../src/runtime.js";
import { HeliosConfigurationError } from "../src/errors.js";
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

function baseOptions() {
  return {
    apiKey: TEST_API_KEY,
    serviceName: "lifecycle-svc",
    endpoint: collector.endpoint,
  };
}

describe("lifecycle", () => {
  it("is unconfigured until configure() and configured afterwards", async () => {
    assert.equal(Helios.isConfigured(), false);
    assert.throws(() => Helios.getTracer(), /not configured/);
    await Helios.configure(baseOptions());
    assert.equal(Helios.isConfigured(), true);
    assert.ok(Helios.getTracer());
  });

  it("treats identical repeated configuration as idempotent", async () => {
    await Helios.configure(baseOptions());
    await Helios.configure(baseOptions());
    assert.equal(Helios.isConfigured(), true);
  });

  it("rejects conflicting reconfiguration without leaking the key", async () => {
    await Helios.configure(baseOptions());
    try {
      await Helios.configure({ ...baseOptions(), serviceName: "other-svc" });
      assert.fail("expected a configuration error");
    } catch (error) {
      assert.ok(error instanceof HeliosConfigurationError);
      assert.match(error.message, /already configured/);
      assert.ok(!error.message.includes(TEST_API_KEY));
    }
  });

  it("a different API key is a conflicting configuration", async () => {
    await Helios.configure(baseOptions());
    const otherKey = "hel_proj_fedcba9876543210_othersecretothersecret";
    try {
      await Helios.configure({ ...baseOptions(), apiKey: otherKey });
      assert.fail("expected a configuration error");
    } catch (error) {
      assert.ok(error instanceof HeliosConfigurationError);
      assert.ok(!error.message.includes(otherKey));
      assert.ok(!error.message.includes(TEST_API_KEY));
    }
  });

  it("allows reconfiguration only after shutdown", async () => {
    await Helios.configure(baseOptions());
    await Helios.shutdown();
    assert.equal(Helios.isConfigured(), false);
    await Helios.configure({ ...baseOptions(), serviceName: "second-svc" });
    assert.equal(Helios.isConfigured(), true);
  });

  it("shutdown is idempotent and flushes pending spans", async () => {
    await Helios.configure(baseOptions());
    Helios.trace("wf.shutdown-flush", () => undefined);
    await Helios.shutdown();
    await Helios.shutdown();
    assert.ok(collector.bodiesInclude("wf.shutdown-flush"));
  });

  it("supports force flush before shutdown", async () => {
    await Helios.configure(baseOptions());
    Helios.trace("wf.flush", () => undefined);
    await Helios.forceFlush();
    assert.ok(collector.bodiesInclude("wf.flush"));
    await Helios.shutdown();
  });

  it("forceFlush before configuration is a safe no-op", async () => {
    await Helios.forceFlush();
    await Helios.shutdown();
  });

  it("refuses to replace a foreign global tracer provider", async () => {
    const foreign = new NodeTracerProvider();
    assert.equal(otelTrace.setGlobalTracerProvider(foreign), true);
    try {
      await Helios.configure(baseOptions());
      assert.fail("expected a configuration error");
    } catch (error) {
      assert.ok(error instanceof HeliosConfigurationError);
      assert.match(error.message, /already registered/);
      assert.equal(Helios.isConfigured(), false);
    } finally {
      await foreign.shutdown();
      otelTrace.disable();
    }
  });

  it("does not register a duplicate global provider on repeated configure", async () => {
    await Helios.configure(baseOptions());
    const provider = otelTrace.getTracerProvider();
    await Helios.configure(baseOptions());
    assert.equal(otelTrace.getTracerProvider(), provider);
  });

  it("rejects extraInstrumentations entries that are not Instrumentations", async () => {
    await assert.rejects(
      Helios.configure({
        ...baseOptions(),
        extraInstrumentations: [{ not: "an instrumentation" }],
      }),
      /Instrumentation interface/,
    );
    assert.equal(Helios.isConfigured(), false);
  });
});
