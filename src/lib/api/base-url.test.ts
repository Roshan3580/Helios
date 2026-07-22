import { describe, expect, test } from "bun:test";

import { normalizeApiBaseUrl, resolveApiBaseUrl } from "./base-url";

describe("normalizeApiBaseUrl", () => {
  test("strips trailing slash", () => {
    expect(normalizeApiBaseUrl("https://api.example.com/")).toBe("https://api.example.com");
  });

  test("rejects credentials", () => {
    expect(() => normalizeApiBaseUrl("https://user:pass@api.example.com")).toThrow(/credentials/);
  });
});

describe("resolveApiBaseUrl", () => {
  test("local defaults to localhost", () => {
    expect(resolveApiBaseUrl({ environment: "local" })).toBe("http://localhost:8000");
  });

  test("staging requires https", () => {
    expect(() =>
      resolveApiBaseUrl({
        environment: "staging",
        configured: "http://helios-api-staging.example.onrender.com",
      }),
    ).toThrow(/HTTPS/);
  });

  test("staging accepts https public url", () => {
    expect(
      resolveApiBaseUrl({
        environment: "staging",
        configured: "https://helios-api-staging.example.onrender.com/",
      }),
    ).toBe("https://helios-api-staging.example.onrender.com");
  });

  test("staging rejects loopback", () => {
    expect(() =>
      resolveApiBaseUrl({
        environment: "staging",
        configured: "https://127.0.0.1:8000",
      }),
    ).toThrow(/loopback/);
  });
});
