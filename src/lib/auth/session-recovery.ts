/**
 * Central, single-flight authentication-recovery state for the authenticated
 * app surface.
 *
 * Checkpoint 25: the previous behavior converted every authenticated API 401
 * (across many concurrent queries) into its own `window.location` redirect to
 * the WorkOS sign-in route, producing an infinite redirect loop and a WorkOS
 * `too_many_requests` (429). This module replaces that with a single observable
 * recovery state. Authenticated requests report a *bounded* failure here after
 * one refresh+retry has already failed; the UI shows one stable panel; and only
 * an explicit user action (the "Sign in again" button) may start a new WorkOS
 * authorization flow — guarded so it can fire at most once.
 *
 * Nothing here stores tokens, cookies, or authorization headers.
 */

import { useSyncExternalStore } from "react";

import { safeReturnPath } from "./return-path";
import type { AuthDiagnostic } from "./token-readiness";

export type SessionRecoveryStatus = "active" | "expired" | "rate_limited";

export interface SessionRecoveryState {
  status: SessionRecoveryStatus;
  /** Seconds to wait before retrying, when the provider supplied Retry-After. */
  retryAfterSeconds: number | null;
  /**
   * Internal, non-sensitive classification of *why* recovery was entered. Used
   * by tests and internal diagnosis; the user-facing panel stays concise and
   * does not vary on it.
   */
  reason: AuthDiagnostic | null;
}

const ACTIVE: SessionRecoveryState = { status: "active", retryAfterSeconds: null, reason: null };

let state: SessionRecoveryState = ACTIVE;
const listeners = new Set<() => void>();
// Single-flight guard: only one explicit sign-in navigation may ever fire.
let signInInFlight = false;

/**
 * Session-identity epoch bookkeeping (Checkpoint 27).
 *
 * A bounded failure recorded against one session identity must stay terminal for
 * that identity — otherwise a re-render would clear the panel the user is
 * reading. But a failure recorded before AuthKit had even resolved the user must
 * not poison a session that subsequently becomes valid without a new login. The
 * epoch is an opaque monotonic counter derived from user/session *change
 * detection only*; no WorkOS identifier is stored here.
 */
let currentEpoch = 0;
let expiredAtEpoch: number | null = null;
let readyNotedEpoch: number | null = null;

function emit(): void {
  for (const listener of listeners) listener();
}

function setState(next: SessionRecoveryState): void {
  if (
    next.status === state.status &&
    next.retryAfterSeconds === state.retryAfterSeconds &&
    next.reason === state.reason
  ) {
    return;
  }
  state = next;
  emit();
}

/**
 * Report that authentication has failed after a bounded attempt: either a
 * backend 401 that survived one refresh+retry, or a token that could not be
 * acquired after `getToken` plus one `refresh`. Flips to a terminal "expired"
 * state; a provider rate-limit takes precedence and is never downgraded.
 *
 * Never call this for a merely *initializing* auth/token state — that is the
 * Checkpoint 27 defect this module's epoch bookkeeping guards against.
 */
export function reportSessionExpired(reason: AuthDiagnostic = "backend_unauthorized"): void {
  if (state.status === "rate_limited") return;
  expiredAtEpoch = currentEpoch;
  setState({ status: "expired", retryAfterSeconds: null, reason });
}

/**
 * Report a provider rate-limit (HTTP 429). Never retried or redirected
 * automatically; Retry-After (seconds) is preserved when available.
 */
export function reportRateLimited(retryAfterSeconds: number | null): void {
  setState({ status: "rate_limited", retryAfterSeconds, reason: "provider_rate_limited" });
}

/**
 * Record the current session-identity epoch. Called whenever AuthKit's
 * user/session identity changes, before token readiness resolves, so a later
 * failure is attributed to the identity that actually failed.
 */
export function setAuthEpoch(epoch: number): void {
  if (epoch === currentEpoch) return;
  currentEpoch = epoch;
}

/**
 * Note that a valid access token became available for `epoch`.
 *
 * Clears a terminal "expired" state only when the readiness belongs to a
 * *different* identity than the one that failed — i.e. a genuinely new
 * session/token transition. Idempotent per epoch, so it can never reset recovery
 * on every render, and it never downgrades a provider rate-limit.
 */
export function noteTokenReadiness(epoch: number): void {
  currentEpoch = epoch;
  if (readyNotedEpoch === epoch) return;
  readyNotedEpoch = epoch;
  if (state.status !== "expired") return;
  if (expiredAtEpoch !== null && expiredAtEpoch === epoch) return;
  expiredAtEpoch = null;
  signInInFlight = false;
  setState(ACTIVE);
}

/** Reset to the active state. Full-page sign-in navigation resets this anyway. */
export function resetSessionRecovery(): void {
  signInInFlight = false;
  currentEpoch = 0;
  expiredAtEpoch = null;
  readyNotedEpoch = null;
  setState(ACTIVE);
}

/**
 * Begin an explicit WorkOS sign-in. ONLY call this from a user gesture (the
 * "Sign in again" button). Single-flight: a second call is a no-op so a
 * double-click or re-render cannot start two authorization flows.
 */
export function beginSignIn(returnPath?: string): void {
  if (typeof window === "undefined") return;
  if (signInInFlight) return;
  const current = window.location.pathname;
  if (current.startsWith("/api/auth/")) return;
  signInInFlight = true;
  const path = safeReturnPath(returnPath ?? current + window.location.search);
  window.location.assign(`/api/auth/sign-in?return=${encodeURIComponent(path)}`);
}

export function getSessionRecoverySnapshot(): SessionRecoveryState {
  return state;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** React binding for the recovery state. */
export function useSessionRecovery(): SessionRecoveryState {
  return useSyncExternalStore(subscribe, getSessionRecoverySnapshot, getSessionRecoverySnapshot);
}
