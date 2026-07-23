/**
 * Shared authenticated-request runner: guaranteed-fresh token, bounded 401
 * refresh+retry, and safe 403/429 handling. This is the single place that
 * encodes the token/refresh/retry policy so no route or hook duplicates it.
 *
 * Policy (Checkpoint 25):
 * - Obtain a fresh token via the SDK immediately before the request.
 * - First 401: force one token refresh and retry the request exactly once.
 * - Retry still 401 (or no token at all): report bounded session expiry — no
 *   automatic redirect. Only the explicit "Sign in again" button navigates.
 * - 403: pass through; never treated as session expiry.
 * - 429: never retried; reported to the recovery state with Retry-After.
 * - Network/cold-start errors (no HTTP status) pass through unchanged so the
 *   existing "backend waking up" handling still applies.
 *
 * The SDK's refresh is itself single-flight (one in-flight refresh promise), so
 * concurrent 401s collapse into a single refresh, and the recovery state flips
 * at most once — no redirect storm.
 */

import { useCallback } from "react";

import { useHeliosAccessToken } from "@/lib/auth/helios-auth";
import { reportRateLimited, reportSessionExpired } from "@/lib/auth/session-recovery";
import { UserApiError } from "@/lib/api/user";

export interface AuthorizedRunnerDeps<T> {
  getToken: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
  call: (token: string) => Promise<T>;
  onExpired: () => void;
  onRateLimited: (retryAfterSeconds: number | null) => void;
}

/** Parse a Retry-After header value (seconds form) into a bounded integer. */
export function parseRetryAfterSeconds(headerValue: string | null | undefined): number | null {
  if (!headerValue) return null;
  const trimmed = headerValue.trim();
  if (/^\d+$/.test(trimmed)) {
    const seconds = Number.parseInt(trimmed, 10);
    return Number.isFinite(seconds) && seconds >= 0 ? seconds : null;
  }
  return null;
}

/**
 * Pure runner (no React) so the retry/expiry/rate-limit policy is unit-testable
 * without a DOM or the SDK.
 */
export async function runAuthorized<T>(deps: AuthorizedRunnerDeps<T>): Promise<T> {
  const token = await deps.getToken();
  if (!token) {
    deps.onExpired();
    throw new UserApiError("Your session has expired.", 401, "");
  }

  try {
    return await deps.call(token);
  } catch (err) {
    if (!(err instanceof UserApiError)) throw err; // network/cold-start: pass through
    if (err.status === 429) {
      deps.onRateLimited(err.retryAfterSeconds ?? null);
      throw err;
    }
    if (err.status !== 401) throw err; // 403 and others are not session expiry

    // First 401: force exactly one refresh, then retry exactly once.
    let refreshed: string | null = null;
    try {
      refreshed = await deps.refresh();
    } catch {
      refreshed = null;
    }
    if (!refreshed) {
      deps.onExpired();
      throw err;
    }
    try {
      return await deps.call(refreshed);
    } catch (retryErr) {
      if (retryErr instanceof UserApiError) {
        if (retryErr.status === 401) deps.onExpired();
        else if (retryErr.status === 429) deps.onRateLimited(retryErr.retryAfterSeconds ?? null);
      }
      throw retryErr;
    }
  }
}

/**
 * React hook returning `run`, which executes an authenticated call with the
 * shared policy. Callers supply only the token-consuming request itself.
 */
export function useAuthorizedRequest(): {
  run: <T>(call: (token: string) => Promise<T>) => Promise<T>;
} {
  const { getAccessToken, refresh } = useHeliosAccessToken();

  const run = useCallback(
    <T>(call: (token: string) => Promise<T>): Promise<T> =>
      runAuthorized<T>({
        getToken: getAccessToken,
        refresh,
        call,
        onExpired: reportSessionExpired,
        onRateLimited: reportRateLimited,
      }),
    [getAccessToken, refresh],
  );

  return { run };
}
