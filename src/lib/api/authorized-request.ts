/**
 * Shared authenticated-request runner: readiness gating, guaranteed-fresh token,
 * bounded 401 refresh+retry, and safe 403/429 handling. This is the single place
 * that encodes the token/refresh/retry policy so no route or hook duplicates it.
 *
 * Policy (Checkpoint 25, corrected by Checkpoint 27):
 * - Wait for AuthKit token readiness first. An auth/token state that is merely
 *   *initializing* never produces a request and never reports expiry.
 * - Obtain a fresh token via the SDK immediately before the request.
 * - No token yet: attempt exactly one bounded refresh before concluding the
 *   token is unavailable. Only then report expiry.
 * - A rejecting WorkOS token server function is classified separately and never
 *   logged (it may carry request/response detail).
 * - First 401: force one token refresh and retry the request exactly once.
 * - Retry still 401: report bounded session expiry — no automatic redirect. Only
 *   the explicit "Sign in again" button navigates.
 * - 403: pass through; never treated as session expiry.
 * - 429: never retried; reported to the recovery state with Retry-After.
 * - Network/cold-start errors (no HTTP status) pass through unchanged so the
 *   existing "backend waking up" handling still applies.
 *
 * The SDK's refresh is itself single-flight (one in-flight refresh promise) and
 * the readiness coordinator collapses the initial acquisition into one flight, so
 * concurrent hooks produce a single token acquisition and the recovery state
 * flips at most once — no redirect storm.
 */

import { useCallback } from "react";

import { useTokenReadiness } from "@/contexts/token-readiness";
import {
  reportRateLimited,
  reportSessionExpired,
  type SessionRecoveryState,
} from "@/lib/auth/session-recovery";
import type { AuthDiagnostic, AuthTokenPhase } from "@/lib/auth/token-readiness";
import { UserApiError } from "@/lib/api/user";

/**
 * Raised when a request is attempted while no WorkOS session exists at all. This
 * is a sign-in boundary, not a fabricated backend 401: the `/app` route's
 * server-side `beforeLoad` owns the actual redirect.
 */
export class NotSignedInError extends Error {
  constructor() {
    super("You are not signed in.");
    this.name = "NotSignedInError";
  }
}

export interface AuthorizedRunnerDeps<T> {
  getToken: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
  call: (token: string) => Promise<T>;
  onExpired: (reason: AuthDiagnostic) => void;
  onRateLimited: (retryAfterSeconds: number | null) => void;
  /**
   * Resolves with the first settled readiness phase. Supplied by the React hook;
   * omitted in pure tests that exercise only the post-readiness policy.
   */
  awaitReady?: () => Promise<AuthTokenPhase>;
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
  // 1. Readiness. An initializing auth/token state resolves here rather than
  //    being misread as expiry, and no request is issued in the meantime.
  if (deps.awaitReady) {
    const phase = await deps.awaitReady();
    if (phase === "unauthenticated") {
      throw new NotSignedInError();
    }
    if (phase === "token_unavailable") {
      deps.onExpired("token_unavailable");
      throw new UserApiError("Your session has expired.", 401, "");
    }
  }

  // 2. Fresh token, with one bounded refresh before concluding it is unavailable.
  let token: string | null;
  try {
    token = await deps.getToken();
  } catch {
    // The WorkOS token server function rejected. The error object is never
    // logged: it may carry request/response detail.
    deps.onExpired("token_server_action_failed");
    throw new UserApiError("Your session has expired.", 401, "");
  }
  if (!token) {
    let acquired: string | null = null;
    try {
      acquired = await deps.refresh();
    } catch {
      deps.onExpired("token_refresh_failed");
      throw new UserApiError("Your session has expired.", 401, "");
    }
    if (!acquired) {
      deps.onExpired("token_unavailable");
      throw new UserApiError("Your session has expired.", 401, "");
    }
    token = acquired;
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
      deps.onExpired("token_refresh_failed");
      throw err;
    }
    try {
      return await deps.call(refreshed);
    } catch (retryErr) {
      if (retryErr instanceof UserApiError) {
        if (retryErr.status === 401) deps.onExpired("backend_unauthorized");
        else if (retryErr.status === 429) deps.onRateLimited(retryErr.retryAfterSeconds ?? null);
      }
      throw retryErr;
    }
  }
}

export interface AuthorizedRequest {
  run: <T>(call: (token: string) => Promise<T>) => Promise<T>;
  /**
   * True only when a backend request may be issued. Data effects MUST use this
   * as a dependency instead of firing on mount — on mount, AuthKit has not yet
   * resolved the user and the SDK returns no token.
   */
  ready: boolean;
  /** Current readiness phase, for callers that distinguish loading from failure. */
  phase: AuthTokenPhase;
  /** Internal, non-sensitive classification. Never rendered verbatim. */
  diagnostic: AuthDiagnostic | null;
  /** True while auth or token initialization is still in progress. */
  tokenLoading: boolean;
  /** Terminal token-acquisition failure (recovery has already been reported). */
  tokenUnavailable: boolean;
  recovery: SessionRecoveryState;
}

/**
 * React hook returning `run` plus the readiness contract. Callers supply only the
 * token-consuming request itself, and gate their effects on `ready`.
 *
 * `run` additionally awaits readiness internally, so a call issued from a user
 * gesture during initialization waits rather than being misclassified as expiry.
 */
export function useAuthorizedRequest(): AuthorizedRequest {
  const readiness = useTokenReadiness();
  const { getAccessToken, refresh, awaitReady } = readiness;

  const run = useCallback(
    <T>(call: (token: string) => Promise<T>): Promise<T> =>
      runAuthorized<T>({
        getToken: getAccessToken,
        refresh,
        call,
        awaitReady,
        onExpired: reportSessionExpired,
        onRateLimited: reportRateLimited,
      }),
    [getAccessToken, refresh, awaitReady],
  );

  return {
    run,
    ready: readiness.ready,
    phase: readiness.phase,
    diagnostic: readiness.diagnostic,
    tokenLoading: readiness.tokenLoading,
    tokenUnavailable: readiness.phase === "token_unavailable",
    recovery: readiness.recovery,
  };
}
