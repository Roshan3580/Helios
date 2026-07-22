import { expect, test } from "@playwright/test";
import { evaluateE2EServerAccess, isLoopbackUrl } from "../src/lib/auth/e2e-guards";

test.describe("E2E auth seam guards", () => {
  test("loopback detection", () => {
    expect(isLoopbackUrl("http://127.0.0.1:9/jwks")).toBeTruthy();
    expect(isLoopbackUrl("http://localhost:9/jwks")).toBeTruthy();
    expect(isLoopbackUrl("https://api.workos.com/sso/jwks/x")).toBeFalsy();
  });

  test("disabled by default", () => {
    const result = evaluateE2EServerAccess({
      nodeEnv: "development",
      e2eTestMode: undefined,
      accessToken: "tok",
      jwksUrl: "http://127.0.0.1:1/jwks",
      issuer: "http://127.0.0.1:1/",
    });
    expect(result.ok).toBeFalsy();
  });

  test("rejected in production", () => {
    const result = evaluateE2EServerAccess({
      nodeEnv: "production",
      e2eTestMode: "true",
      accessToken: "tok",
      jwksUrl: "http://127.0.0.1:1/jwks",
      issuer: "http://127.0.0.1:1/",
    });
    expect(result.ok).toBeFalsy();
    if (!result.ok) expect(result.reason).toBe("e2e_auth_disabled_in_production");
  });

  test("rejected for non-loopback JWKS", () => {
    const result = evaluateE2EServerAccess({
      nodeEnv: "development",
      e2eTestMode: "true",
      accessToken: "tok",
      jwksUrl: "https://api.workos.com/sso/jwks/x",
      issuer: "https://api.workos.com/user_management/x",
    });
    expect(result.ok).toBeFalsy();
  });

  test("session route is available only under harness", async ({ request }) => {
    // When harness is running, session returns 200. Without harness this file
    // is not executed (baseURL missing). Assert shape when present.
    const res = await request.get("/api/e2e/session");
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.accessToken).toBeTruthy();
    expect(body.organizationId).toBeTruthy();
    // Token must not be a VITE_ build-time constant pattern from env example.
    expect(String(body.accessToken)).not.toContain("VITE_");
  });
});
