import { afterEach, describe, expect, test } from "bun:test";

import {
  beginSignIn,
  getSessionRecoverySnapshot,
  reportRateLimited,
  reportSessionExpired,
  resetSessionRecovery,
} from "./session-recovery";

afterEach(() => {
  resetSessionRecovery();
  // @ts-expect-error test cleanup of any stubbed window
  delete globalThis.window;
});

describe("session-recovery store", () => {
  test("starts active", () => {
    expect(getSessionRecoverySnapshot().status).toBe("active");
  });

  test("reportSessionExpired flips to expired and is idempotent (single-flight)", () => {
    reportSessionExpired();
    reportSessionExpired();
    reportSessionExpired();
    expect(getSessionRecoverySnapshot().status).toBe("expired");
  });

  test("reportRateLimited sets rate_limited with Retry-After", () => {
    reportRateLimited(30);
    const s = getSessionRecoverySnapshot();
    expect(s.status).toBe("rate_limited");
    expect(s.retryAfterSeconds).toBe(30);
  });

  test("rate_limited is not downgraded to expired", () => {
    reportRateLimited(15);
    reportSessionExpired();
    expect(getSessionRecoverySnapshot().status).toBe("rate_limited");
  });

  test("reset returns to active", () => {
    reportSessionExpired();
    resetSessionRecovery();
    expect(getSessionRecoverySnapshot().status).toBe("active");
  });
});

describe("beginSignIn single-flight navigation", () => {
  test("navigates at most once even when called repeatedly", () => {
    const assigns: string[] = [];
    // Minimal window stub for the non-DOM test runtime.
    // @ts-expect-error partial window stub
    globalThis.window = {
      location: {
        pathname: "/app/dashboard",
        search: "",
        assign: (url: string) => assigns.push(url),
      },
    };

    beginSignIn();
    beginSignIn();
    beginSignIn();

    expect(assigns).toHaveLength(1);
    expect(assigns[0]).toContain("/api/auth/sign-in?return=");
  });

  test("does nothing on auth routes (avoids self-loop)", () => {
    const assigns: string[] = [];
    // @ts-expect-error partial window stub
    globalThis.window = {
      location: {
        pathname: "/api/auth/callback",
        search: "",
        assign: (url: string) => assigns.push(url),
      },
    };
    beginSignIn();
    expect(assigns).toHaveLength(0);
  });
});
