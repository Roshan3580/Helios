import { describe, expect, test } from "bun:test";

import { parseRetryAfterSeconds, runAuthorized } from "./authorized-request";
import { UserApiError } from "./user";

function deps<T>(overrides: Partial<Parameters<typeof runAuthorized<T>>[0]>) {
  const events: string[] = [];
  const base = {
    getToken: async () => "tok-1",
    refresh: async () => "tok-2",
    call: async (_token: string) => ({ ok: true }) as unknown as T,
    onExpired: () => events.push("expired"),
    onRateLimited: (s: number | null) => events.push(`rate:${s}`),
  };
  return { d: { ...base, ...overrides }, events };
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

  test("no token → reports expired and throws 401, never calls", async () => {
    let called = false;
    const { d, events } = deps({
      getToken: async () => null,
      call: async () => {
        called = true;
        return {};
      },
    });
    await expect(runAuthorized(d)).rejects.toBeInstanceOf(UserApiError);
    expect(called).toBe(false);
    expect(events).toContain("expired");
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
    expect(events).not.toContain("expired");
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
    expect(events.filter((e) => e === "expired")).toHaveLength(1);
  });

  test("failed refresh → expired, no retry attempt", async () => {
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
    expect(events).toContain("expired");
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
    expect(events).not.toContain("expired");
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
    expect(events).not.toContain("expired");
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
