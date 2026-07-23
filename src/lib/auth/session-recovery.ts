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

export type SessionRecoveryStatus = "active" | "expired" | "rate_limited";

export interface SessionRecoveryState {
  status: SessionRecoveryStatus;
  /** Seconds to wait before retrying, when the provider supplied Retry-After. */
  retryAfterSeconds: number | null;
}

const ACTIVE: SessionRecoveryState = { status: "active", retryAfterSeconds: null };

let state: SessionRecoveryState = ACTIVE;
const listeners = new Set<() => void>();
// Single-flight guard: only one explicit sign-in navigation may ever fire.
let signInInFlight = false;

function emit(): void {
  for (const listener of listeners) listener();
}

function setState(next: SessionRecoveryState): void {
  if (next.status === state.status && next.retryAfterSeconds === state.retryAfterSeconds) {
    return;
  }
  state = next;
  emit();
}

/**
 * Report that authentication has failed after a bounded refresh+retry. Flips to
 * a terminal "expired" state exactly once; a provider rate-limit takes
 * precedence and is never downgraded to "expired".
 */
export function reportSessionExpired(): void {
  if (state.status === "rate_limited") return;
  setState({ status: "expired", retryAfterSeconds: null });
}

/**
 * Report a provider rate-limit (HTTP 429). Never retried or redirected
 * automatically; Retry-After (seconds) is preserved when available.
 */
export function reportRateLimited(retryAfterSeconds: number | null): void {
  setState({ status: "rate_limited", retryAfterSeconds });
}

/** Reset to the active state. Full-page sign-in navigation resets this anyway. */
export function resetSessionRecovery(): void {
  signInInFlight = false;
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
