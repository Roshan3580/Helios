import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  DEFAULT_ENDPOINT,
  DEFAULT_TIMEOUT_MILLIS,
  TRACES_PATH,
  normalizeEndpoint,
  resolveConfig,
} from "../src/config.js";
import { HeliosConfigurationError } from "../src/errors.js";
import { TEST_API_KEY } from "./helpers/reset.js";

const BASE = { apiKey: TEST_API_KEY, serviceName: "svc" };
const EMPTY_ENV: Record<string, string | undefined> = {};

describe("configuration resolution", () => {
  it("resolves explicit configuration", () => {
    const config = resolveConfig(
      {
        ...BASE,
        endpoint: "https://helios.example.com",
        serviceVersion: "1.2.3",
        environment: "development",
      },
      EMPTY_ENV,
    );
    assert.equal(config.apiKey, TEST_API_KEY);
    assert.equal(config.serviceName, "svc");
    assert.equal(config.serviceVersion, "1.2.3");
    assert.equal(config.environment, "development");
    assert.equal(config.endpoint, "https://helios.example.com");
    assert.equal(config.tracesEndpoint, `https://helios.example.com${TRACES_PATH}`);
    assert.equal(config.timeoutMillis, DEFAULT_TIMEOUT_MILLIS);
    assert.equal(config.captureContent, false);
    assert.equal(config.diagnostics, "none");
    assert.deepEqual(config.instrumentations, { node: false, openai: false });
  });

  it("resolves configuration from environment variables", () => {
    const config = resolveConfig(
      {},
      {
        HELIOS_API_KEY: TEST_API_KEY,
        HELIOS_ENDPOINT: "https://helios.example.com/",
        HELIOS_SERVICE_NAME: "env-svc",
        HELIOS_SERVICE_VERSION: "9.9.9",
        HELIOS_ENVIRONMENT: "staging",
      },
    );
    assert.equal(config.serviceName, "env-svc");
    assert.equal(config.serviceVersion, "9.9.9");
    assert.equal(config.environment, "staging");
    assert.equal(config.endpoint, "https://helios.example.com");
  });

  it("prefers explicit options over environment variables", () => {
    const config = resolveConfig(
      { ...BASE, environment: "explicit" },
      { HELIOS_ENVIRONMENT: "from-env", HELIOS_SERVICE_NAME: "ignored" },
    );
    assert.equal(config.environment, "explicit");
    assert.equal(config.serviceName, "svc");
  });

  it("falls back to OTEL_SERVICE_NAME", () => {
    const config = resolveConfig(
      { apiKey: TEST_API_KEY },
      { OTEL_SERVICE_NAME: "otel-svc" },
    );
    assert.equal(config.serviceName, "otel-svc");
  });

  it("requires an API key", () => {
    assert.throws(
      () => resolveConfig({ serviceName: "svc" }, EMPTY_ENV),
      (error: unknown) =>
        error instanceof HeliosConfigurationError && /apiKey is required/.test(error.message),
    );
  });

  it("rejects malformed API keys without echoing them", () => {
    const secret = "sk-this-is-not-a-helios-key-123456";
    try {
      resolveConfig({ apiKey: secret, serviceName: "svc" }, EMPTY_ENV);
      assert.fail("expected a configuration error");
    } catch (error) {
      assert.ok(error instanceof HeliosConfigurationError);
      assert.ok(!error.message.includes(secret));
      assert.match(error.message, /hel_proj_/);
    }
  });

  it("requires a service name", () => {
    assert.throws(
      () => resolveConfig({ apiKey: TEST_API_KEY }, EMPTY_ENV),
      /serviceName is required/,
    );
  });

  it("defaults the endpoint to localhost", () => {
    const config = resolveConfig(BASE, EMPTY_ENV);
    assert.equal(config.endpoint, DEFAULT_ENDPOINT);
    assert.equal(config.tracesEndpoint, `${DEFAULT_ENDPOINT}${TRACES_PATH}`);
  });

  it("validates timeout bounds", () => {
    assert.equal(resolveConfig({ ...BASE, timeoutMillis: 5000 }, EMPTY_ENV).timeoutMillis, 5000);
    assert.throws(() => resolveConfig({ ...BASE, timeoutMillis: 0 }, EMPTY_ENV), /timeoutMillis/);
    assert.throws(
      () => resolveConfig({ ...BASE, timeoutMillis: 999_999 }, EMPTY_ENV),
      /timeoutMillis/,
    );
    assert.throws(
      () => resolveConfig({ ...BASE, timeoutMillis: 10.5 }, EMPTY_ENV),
      /timeoutMillis/,
    );
  });

  it("validates batch bounds", () => {
    const config = resolveConfig(
      { ...BASE, batch: { scheduledDelayMillis: 100, maxQueueSize: 100, maxExportBatchSize: 50 } },
      EMPTY_ENV,
    );
    assert.deepEqual(config.batch, {
      scheduledDelayMillis: 100,
      maxQueueSize: 100,
      maxExportBatchSize: 50,
    });
    assert.throws(
      () => resolveConfig({ ...BASE, batch: { maxQueueSize: 0 } }, EMPTY_ENV),
      /maxQueueSize/,
    );
    assert.throws(
      () =>
        resolveConfig(
          { ...BASE, batch: { maxQueueSize: 10, maxExportBatchSize: 20 } },
          EMPTY_ENV,
        ),
      /must not exceed/,
    );
  });

  it("parses capture-content booleans strictly", () => {
    assert.equal(
      resolveConfig(BASE, { HELIOS_CAPTURE_CONTENT: "true" }).captureContent,
      true,
    );
    assert.equal(
      resolveConfig(BASE, { HELIOS_CAPTURE_CONTENT: "false" }).captureContent,
      false,
    );
    assert.throws(
      () => resolveConfig(BASE, { HELIOS_CAPTURE_CONTENT: "maybe" }),
      /HELIOS_CAPTURE_CONTENT/,
    );
  });

  it("rejects secret-like and protected resource attributes", () => {
    assert.throws(
      () =>
        resolveConfig(
          { ...BASE, resourceAttributes: { "team.api_key": "x" } },
          EMPTY_ENV,
        ),
      /secret-like/,
    );
    assert.throws(
      () =>
        resolveConfig(
          { ...BASE, resourceAttributes: { "service.name": "override" } },
          EMPTY_ENV,
        ),
      /managed by the SDK/,
    );
    assert.throws(
      () =>
        resolveConfig(
          { ...BASE, resourceAttributes: { "helios.sdk.name": "spoof" } },
          EMPTY_ENV,
        ),
      /reserved prefix/,
    );
  });

  it("caps and keeps valid custom resource attributes", () => {
    const config = resolveConfig(
      { ...BASE, resourceAttributes: { "team.name": "search", "region": "eu-west-1" } },
      EMPTY_ENV,
    );
    assert.deepEqual(config.resourceAttributes, {
      "team.name": "search",
      region: "eu-west-1",
    });
    const tooMany = Object.fromEntries(
      Array.from({ length: 40 }, (_, index) => [`attr.${index}`, "v"]),
    );
    assert.throws(
      () => resolveConfig({ ...BASE, resourceAttributes: tooMany }, EMPTY_ENV),
      /too many resource attributes/,
    );
  });
});

describe("endpoint normalization", () => {
  it("appends the canonical traces path to a base URL", () => {
    assert.deepEqual(normalizeEndpoint("https://helios.example.com"), {
      endpoint: "https://helios.example.com",
      tracesEndpoint: "https://helios.example.com/v1/otlp/traces",
    });
  });

  it("strips trailing slashes", () => {
    assert.equal(
      normalizeEndpoint("https://helios.example.com///").tracesEndpoint,
      "https://helios.example.com/v1/otlp/traces",
    );
  });

  it("does not double-append the traces path", () => {
    const normalized = normalizeEndpoint("https://helios.example.com/v1/otlp/traces");
    assert.equal(normalized.tracesEndpoint, "https://helios.example.com/v1/otlp/traces");
    assert.equal(normalized.endpoint, "https://helios.example.com");
  });

  it("keeps a path prefix in front of the traces path", () => {
    assert.equal(
      normalizeEndpoint("https://example.com/helios").tracesEndpoint,
      "https://example.com/helios/v1/otlp/traces",
    );
  });

  it("allows plain HTTP for loopback hosts", () => {
    for (const url of [
      "http://localhost:8000",
      "http://127.0.0.1:9999",
      "http://127.1.2.3:9999",
      "http://[::1]:8000",
      "http://api.localhost",
    ]) {
      assert.ok(normalizeEndpoint(url).tracesEndpoint.endsWith(TRACES_PATH));
    }
  });

  it("rejects plain HTTP for non-loopback hosts unless explicitly allowed", () => {
    assert.throws(
      () => normalizeEndpoint("http://helios.example.com"),
      /plain HTTP is only allowed for loopback/,
    );
    assert.ok(
      normalizeEndpoint("http://helios.internal:8000", { allowInsecureHttp: true })
        .tracesEndpoint,
    );
  });

  it("rejects unsupported protocols, credentials, and query parameters", () => {
    assert.throws(() => normalizeEndpoint("ftp://helios.example.com"), /protocol/);
    assert.throws(() => normalizeEndpoint("not a url"), /not a valid URL/);
    assert.throws(
      () => normalizeEndpoint("https://user:pass@helios.example.com"),
      /must not contain credentials/,
    );
    assert.throws(
      () => normalizeEndpoint("https://helios.example.com?key=abc"),
      /query parameters/,
    );
  });
});
