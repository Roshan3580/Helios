import { describe, expect, test } from "bun:test";

import { classifyBackendFailure, COLD_START_MESSAGE, isColdStart } from "./cold-start";

describe("classifyBackendFailure", () => {
  test("auth codes are never a cold start", () => {
    expect(classifyBackendFailure(401)).toBe("auth");
    expect(classifyBackendFailure(403)).toBe("auth");
    expect(isColdStart(401)).toBe(false);
    expect(isColdStart(403)).toBe(false);
  });

  test("gateway/unavailable/timeout codes are cold starts", () => {
    for (const status of [502, 503, 504, 408]) {
      expect(classifyBackendFailure(status)).toBe("cold_start");
    }
  });

  test("no HTTP response (network error) is a cold start", () => {
    expect(classifyBackendFailure(null)).toBe("cold_start");
    expect(classifyBackendFailure(undefined)).toBe("cold_start");
    expect(classifyBackendFailure(0)).toBe("cold_start");
  });

  test("real application errors are surfaced, not hidden as cold start", () => {
    expect(classifyBackendFailure(404)).toBe("error");
    expect(classifyBackendFailure(422)).toBe("error");
    expect(classifyBackendFailure(500)).toBe("error");
  });

  test("exports a bounded, human-readable waking-up message", () => {
    expect(COLD_START_MESSAGE).toContain("waking up");
  });
});
