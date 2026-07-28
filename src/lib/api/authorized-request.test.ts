import { describe, expect, test } from "bun:test";

import { NotSignedInError, parseRetryAfterSeconds, runAuthorized } from "./authorized-request";
import { UserApiError } from "./user";
import type { AuthDiagnostic } from "@/lib/auth/token-readiness";

function deps<T>(overrides: Partial<Parameters<typeof runAuthorized<T>>[0]>) {
  const events: string[] = [];
  const base = {
    getToken: async () => "tok-1",
    refresh: async () => "tok-2",
    call: async (_token: string) => ({ ok: true }) as unknown as T,
    onExpired: (reason: AuthDiagnostic) => events.push(`expired:${reason}`),
    onRateLimited: (s: number | null) => events.push(`rate:${s}`),
  };
  return { d: { ...base, ...overrides }, events };
}

/** Any expiry report, regardless of classification. */
function expiredEvents(events: string[]): string[] {
  return events.filter((event) => event.startsWith("expired:"));
}

describe("parseRetryAfterSeconds", () => {
  test("parses numeric seconds", () => {
    expect(parseRetryAfterSeconds("30")).toBe(30);
    expect(parseRetryAfterSeconds("0")).toBe(0);
  });
  test("ignores non-numeric / missing", () => {
    expect(parseRetryAfterSeconds(null)).toBeNull();
    expect(parseRetryAfterSeconds("")).toBeNull();
    expect(parseRetryAfterSeconds("Wed, 21 Oct 2099 07:28:00 GMT")).toBeNull();
  });
});

describe("runAuthorized", () => {
  test("uses a fresh token and returns the result", async () => {
    const seen: string[] = [];
    const { d } = deps({
      call: async (t) => {
        seen.push(t);
        return { v: 1 };
      },
    });
    const result = await runAuthorized(d);
    expect(result).toEqual({ v: 1 });
    expect(seen).toEqual(["tok-1"]); // fresh token from getToken, no refresh
  });

  test("no token, and no token after one bounded refresh → expired, never calls", async () => {
    // Checkpoint 27: a missing token now costs exactly one bounded refresh
    // attempt before expiry is concluded, rather than expiring immediately.
    let called = false;
    let refreshCount = 0;
    const { d, events } = deps({
      getToken: async () => null,
      refresh: async () => {
        refreshCount += 1;
        return null;
      },
      call: async () => {
        called = true;
        return {};
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(called).toBe(false);
    expect(refreshCount).toBe(1);
    expect(events).toContain("expired:token_unavailable");
  });

  test("no token but a successful bounded refresh → calls once, no expiry", async () => {
    const tokens: string[] = [];
    let refreshCount = 0;
    const { d, events } = deps({
      getToken: async () => null,
      refresh: async () => {
        refreshCount += 1;
        return "tok-2";
      },
      call: async (t) => {
        tokens.push(t);
        return { v: "ok" };
      },
    });
    await expect(runAuthorized(d)).resolves.toEqual({ v: "ok" });
    expect(tokens).toEqual(["tok-2"]);
    expect(refreshCount).toBe(1);
    expect(expiredEvents(events)).toEqual([]);
  });

  test("a rejecting token server function is classified, not leaked, and never calls", async () => {
    let called = false;
    const { d, events } = deps({
      getToken: async () => {
        throw new Error("workos server function failed");
      },
      call: async () => {
        called = true;
        return {};
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(called).toBe(false);
    expect(events).toContain("expired:token_server_action_failed");
  });

  test("a rejecting refresh during acquisition is classified separately", async () => {
    const { d, events } = deps({
      getToken: async () => null,
      refresh: async () => {
        throw new Error("refresh failed");
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(events).toContain("expired:token_refresh_failed");
  });

  test("first 401 refreshes once and retries exactly once (success)", async () => {
    const tokens: string[] = [];
    let refreshCount = 0;
    const { d, events } = deps({
      call: async (t) => {
        tokens.push(t);
        if (t === "tok-1") throw new UserApiError("unauthorized", 401, "/x");
        return { v: "ok" };
      },
      refresh: async () => {
        refreshCount += 1;
        return "tok-2";
      },
    });
    const result = await runAuthorized(d);
    expect(result).toEqual({ v: "ok" });
    expect(tokens).toEqual(["tok-1", "tok-2"]); // exactly one retry
    expect(refreshCount).toBe(1);
    expect(expiredEvents(events)).toEqual([]);
  });

  test("second 401 stops after one retry and reports expired", async () => {
    const tokens: string[] = [];
    const { d, events } = deps({
      call: async (t) => {
        tokens.push(t);
        throw new UserApiError("unauthorized", 401, "/x");
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(tokens).toEqual(["tok-1", "tok-2"]); // never a third attempt
    expect(expiredEvents(events)).toEqual(["expired:backend_unauthorized"]);
  });

  test("failed refresh after a 401 → expired, no retry attempt", async () => {
    const tokens: string[] = [];
    const { d, events } = deps({
      call: async (t) => {
        tokens.push(t);
        throw new UserApiError("unauthorized", 401, "/x");
      },
      refresh: async () => null,
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(tokens).toEqual(["tok-1"]); // refresh failed → no retry call
    expect(events).toContain("expired:token_refresh_failed");
  });

  test("403 is not session expiry: no refresh, no expired, rethrows", async () => {
    let refreshCount = 0;
    const { d, events } = deps({
      call: async () => {
        throw new UserApiError("forbidden", 403, "/x");
      },
      refresh: async () => {
        refreshCount += 1;
        return "tok-2";
      },
    });
    await expect(runAuthorized(d)).rejects.toMatchObject({ status: 403 });
    expect(refreshCount).toBe(0);
    expect(expiredEvents(events)).toEqual([]);
  });

  test("429 reports rate-limit with Retry-After, never retries or expires", async () => {
    let calls = 0;
    const { d, events } = deps({
      call: async () => {
        calls += 1;
        throw new UserApiError("rate limited", 429, "/x", undefined, 42);
      },
    });
    await expect(runAuthorized(d)).rejects.toMatchObject({ status: 429 });
    expect(calls).toBe(1); // no retry
    expect(events).toContain("rate:42");
    expect(expiredEvents(events)).toEqual([]);
  });

  test("network error (non-UserApiError) passes through untouched", async () => {
    const { d, events } = deps({
      call: async () => {
        throw new TypeError("Failed to fetch");
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(TypeError);
    expect(events).toEqual([]); // not expiry, not rate-limit
  });
});

describe("runAuthorized readiness gating (Checkpoint 27)", () => {
  test("waits for readiness before issuing the request", async () => {
    const order: string[] = [];
    let releaseReady: ((phase: "token_ready") => void) | null = null;
    const { d, events } = deps({
      awaitReady: () =>
        new Promise((resolve) => {
          order.push("awaiting-readiness");
          releaseReady = resolve;
        }),
      getToken: async () => {
        order.push("get-token");
        return "tok-1";
      },
      call: async () => {
        order.push("backend-call");
        return { v: 1 };
      },
    });

    const pending = runAuthorized(d);
    await Promise.resolve();
    // Critically: nothing has touched the token or the backend yet.
    expect(order).toEqual(["awaiting-readiness"]);

    releaseReady!("token_ready");
    await expect(pending).resolves.toEqual({ v: 1 });
    expect(order).toEqual(["awaiting-readiness", "get-token", "backend-call"]);
    expect(expiredEvents(events)).toEqual([]);
  });

  test("a settled token_unavailable phase expires without calling the backend", async () => {
    let called = false;
    const { d, events } = deps({
      awaitReady: async () => "token_unavailable",
      call: async () => {
        called = true;
        return {};
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(called).toBe(false);
    expect(events).toContain("expired:token_unavailable");
  });

  test("an unauthenticated phase is a sign-in boundary, not a fabricated 401", async () => {
    let called = false;
    const { d, events } = deps({
      awaitReady: async () => "unauthenticated",
      call: async () => {
        called = true;
        return {};
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(NotSignedInError);
    expect(called).toBe(false);
    // Never reported as session expiry: the route's server-side redirect owns it.
    expect(expiredEvents(events)).toEqual([]);
  });
});
