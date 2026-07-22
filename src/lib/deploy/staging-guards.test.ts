import { describe, expect, test } from "bun:test";

import { evaluateStagingFrontendContract } from "../deploy/staging-guards";

describe("evaluateStagingFrontendContract", () => {
  test("local is always ok", () => {
    expect(evaluateStagingFrontendContract({ heliosEnvironment: "local" }).ok).toBe(true);
  });

  test("staging rejects e2e mode and tokens", () => {
    const result = evaluateStagingFrontendContract({
      heliosEnvironment: "staging",
      e2eTestMode: "true",
      e2eAccessToken: "tok",
      viteE2eTestMode: "true",
      apiBaseUrl: "https://helios-api-staging.example.onrender.com",
      workosRedirectUri: "https://helios-staging.example.vercel.app/api/auth/callback",
      workosCookiePassword: "x".repeat(32),
      frontendOrigin: "https://helios-staging.example.vercel.app",
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.reasons).toContain("e2e_mode_forbidden_in_staging");
      expect(result.reasons).toContain("e2e_access_token_forbidden_in_staging");
    }
  });

  test("staging accepts fixed hostname contract", () => {
    const result = evaluateStagingFrontendContract({
      heliosEnvironment: "staging",
      e2eTestMode: "false",
      apiBaseUrl: "https://helios-api-staging.example.onrender.com",
      workosRedirectUri: "https://helios-staging.example.vercel.app/api/auth/callback",
      workosCookiePassword: "x".repeat(32),
      frontendOrigin: "https://helios-staging.example.vercel.app",
    });
    expect(result).toEqual({ ok: true });
  });
});
