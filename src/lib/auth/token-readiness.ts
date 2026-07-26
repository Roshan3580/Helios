/**
 * AuthKit access-token readiness contract (Checkpoint 27).
 *
 * WHY THIS EXISTS
 * ---------------
 * A valid WorkOS session and a usable access token do NOT become available in
 * the same render. `AuthKitProvider` holds `user`/`sessionId` in React state and
 * populates them from an async `getAuthAction()` RPC issued by its own mount
 * effect, while the access token lives in a separate module-level store that is
 * only filled afterwards. React runs child effects before parent effects, so any
 * data hook mounted under the provider runs *before* the provider has even asked
 * who the user is. At that moment the SDK's `getAccessToken()` returns
 * `undefined` immediately — without contacting WorkOS at all — because it
 * short-circuits on a null user.
 *
 * Treating that `undefined` as "session expired" is the Checkpoint 27 defect: no
 * backend request was ever attempted, yet the app rendered a terminal expiry
 * panel. This module encodes the missing distinction between *initializing* and
 * *unavailable*.
 *
 * TWO SDK BEHAVIORS THIS MUST TOLERATE
 * ------------------------------------
 * 1. `useAccessToken().loading` is `false` while `useAuth().loading` is `true`
 *    (its initial value is `Boolean(user && …)`, which is false when the user is
 *    still null). Auth loading must therefore be checked separately; SDK token
 *    `loading` alone is not a sufficient gate.
 * 2. There is a legitimate render where the user is valid, token `loading` is
 *    `false`, and no token exists yet — the commit between the auth RPC
 *    resolving and the SDK's token effect running. "No token and not loading" is
 *    consequently NEVER terminal on its own.
 *
 * Terminality is decided only by an explicit *bounded acquisition attempt*
 * (`getToken` then one `refresh`), never by observing a transient state. No
 * timers, no polling, and no token value is stored here — only whether one
 * exists.
 */

/** Coarse phase a caller keys its data effects on. */
export type AuthTokenPhase =
  | "auth_initializing"
  | "token_initializing"
  | "token_ready"
  | "token_unavailable"
  | "unauthenticated";

/**
 * Internal, non-sensitive failure classification. Deliberately carries no JWT,
 * claims, cookie, header, email, WorkOS identifier, or environment value — these
 * are constant strings safe to surface in tests and internal state.
 */
export type AuthDiagnostic =
  | "auth_initializing"
  | "token_initializing"
  | "token_unavailable"
  | "token_refresh_failed"
  | "token_server_action_failed"
  | "backend_unauthorized"
  | "provider_rate_limited";

/** Lifecycle of the bounded token-acquisition attempt. */
export type AcquisitionState = "idle" | "pending" | "ready" | "failed";

export interface AcquisitionSnapshot {
  state: AcquisitionState;
  diagnostic: AuthDiagnostic | null;
}

export interface AcquisitionResult {
  state: "ready" | "failed";
  diagnostic: AuthDiagnostic | null;
}

export interface TokenPhaseInput {
  /** AuthKit is still resolving the current user/session. */
  authLoading: boolean;
  /** A valid WorkOS (or E2E) user exists. */
  hasUser: boolean;
  /** The SDK already holds a non-empty access token. */
  hasToken: boolean;
  /** State of the bounded acquisition attempt for the current session. */
  acquisition: AcquisitionState;
}

/**
 * Map observable auth/token state onto the readiness contract.
 *
 * Ordering is deliberate: auth loading dominates (the SDK reports token
 * `loading: false` during it), an absent user after loading is a sign-in
 * boundary rather than a backend 401, and an unresolved token is *initializing*
 * unless a bounded acquisition attempt has actually failed.
 */
export function resolveTokenPhase(input: TokenPhaseInput): AuthTokenPhase {
  if (input.authLoading) return "auth_initializing";
  if (!input.hasUser) return "unauthenticated";
  if (input.hasToken) return "token_ready";
  if (input.acquisition === "ready") return "token_ready";
  if (input.acquisition === "failed") return "token_unavailable";
  // "idle" and "pending": the token is still being established. Never terminal.
  return "token_initializing";
}

/** True when an authenticated backend request may be issued. */
export function phaseAllowsRequest(phase: AuthTokenPhase): boolean {
  return phase === "token_ready";
}

/** True when the phase has settled and will not advance without new input. */
export function isSettledPhase(phase: AuthTokenPhase): boolean {
  return phase === "token_ready" || phase === "token_unavailable" || phase === "unauthenticated";
}

/** Diagnostic for a phase, for internal state and tests only. */
export function phaseDiagnostic(
  phase: AuthTokenPhase,
  acquisitionDiagnostic: AuthDiagnostic | null,
): AuthDiagnostic | null {
  if (phase === "auth_initializing") return "auth_initializing";
  if (phase === "token_initializing") return "token_initializing";
  if (phase === "token_unavailable") return acquisitionDiagnostic ?? "token_unavailable";
  return null;
}

export interface TokenAcquisitionDeps {
  getToken: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
}

export interface TokenAcquisitionStore {
  /** Install the SDK-backed token functions. Idempotent for equal identities. */
  configure: (deps: TokenAcquisitionDeps) => void;
  /**
   * Bounded, single-flight acquisition: one `getToken`, then at most one
   * `refresh`. Concurrent callers share the same flight; a settled result is
   * returned without re-attempting.
   */
  acquire: () => Promise<AcquisitionResult>;
  /** Discard state when the user/session identity changes. */
  resetForEpoch: (epoch: number) => void;
  getSnapshot: () => AcquisitionSnapshot;
  getServerSnapshot: () => AcquisitionSnapshot;
  subscribe: (listener: () => void) => () => void;
  /** Test-only full reset. */
  reset: () => void;
}

const IDLE: AcquisitionSnapshot = { state: "idle", diagnostic: null };
const READY: AcquisitionSnapshot = { state: "ready", diagnostic: null };

/**
 * Factory for the acquisition coordinator. Extracted from React so the bounded
 * single-flight policy is unit-testable without a DOM or the SDK.
 */
export function createTokenAcquisitionStore(): TokenAcquisitionStore {
  let snapshot: AcquisitionSnapshot = IDLE;
  let deps: TokenAcquisitionDeps | null = null;
  let inflight: Promise<AcquisitionResult> | null = null;
  let epoch = 0;
  const listeners = new Set<() => void>();

  function emit(): void {
    for (const listener of listeners) listener();
  }

  function setSnapshot(next: AcquisitionSnapshot): void {
    if (next.state === snapshot.state && next.diagnostic === snapshot.diagnostic) return;
    snapshot = next;
    emit();
  }

  function settle(
    forEpoch: number,
    state: "ready" | "failed",
    diagnostic: AuthDiagnostic | null,
  ): AcquisitionResult {
    // A flight started before a session change must not overwrite newer state.
    if (forEpoch === epoch) {
      setSnapshot(state === "ready" ? READY : { state: "failed", diagnostic });
    }
    return { state, diagnostic };
  }

  return {
    configure(next) {
      if (deps && deps.getToken === next.getToken && deps.refresh === next.refresh) return;
      deps = next;
    },

    acquire() {
      if (snapshot.state === "ready") {
        return Promise.resolve<AcquisitionResult>({ state: "ready", diagnostic: null });
      }
      if (snapshot.state === "failed") {
        // Bounded: a failed attempt is not retried until the session changes.
        return Promise.resolve<AcquisitionResult>({
          state: "failed",
          diagnostic: snapshot.diagnostic,
        });
      }
      if (inflight) return inflight;
      if (!deps) {
        // No SDK functions installed yet: still initializing, not a failure.
        return Promise.resolve<AcquisitionResult>({
          state: "failed",
          diagnostic: "token_initializing",
        });
      }

      const active = deps;
      const forEpoch = epoch;
      setSnapshot({ state: "pending", diagnostic: null });

      const attempt = (async (): Promise<AcquisitionResult> => {
        let token: string | null = null;
        try {
          token = await active.getToken();
        } catch {
          // The WorkOS token server function rejected. Never log the error
          // object: it may carry request/response detail.
          return settle(forEpoch, "failed", "token_server_action_failed");
        }
        if (token) return settle(forEpoch, "ready", null);

        let refreshed: string | null = null;
        try {
          refreshed = await active.refresh();
        } catch {
          return settle(forEpoch, "failed", "token_refresh_failed");
        }
        if (refreshed) return settle(forEpoch, "ready", null);
        return settle(forEpoch, "failed", "token_unavailable");
      })();

      inflight = attempt;
      void attempt.finally(() => {
        if (inflight === attempt) inflight = null;
      });
      return attempt;
    },

    resetForEpoch(nextEpoch) {
      if (nextEpoch === epoch) return;
      epoch = nextEpoch;
      inflight = null;
      setSnapshot(IDLE);
    },

    getSnapshot: () => snapshot,
    getServerSnapshot: () => IDLE,

    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },

    reset() {
      snapshot = IDLE;
      deps = null;
      inflight = null;
      epoch = 0;
      listeners.clear();
    },
  };
}

export interface ReadinessGate {
  /** Publish the current phase; resolves waiters once the phase is settled. */
  set: (phase: AuthTokenPhase) => void;
  /**
   * Resolve with the first settled phase. Returns immediately when already
   * settled. Driven purely by SDK-observed state transitions — no timer, no
   * polling, and no timeout-based success assumption.
   */
  wait: () => Promise<AuthTokenPhase>;
  peek: () => AuthTokenPhase;
  reset: () => void;
}

/**
 * Bridge between React phase state and the imperative `run()` path, so a call
 * issued from a user gesture during initialization waits for readiness instead
 * of being misclassified as an expired session.
 */
export function createReadinessGate(): ReadinessGate {
  let phase: AuthTokenPhase = "auth_initializing";
  let waiters: Array<(phase: AuthTokenPhase) => void> = [];

  return {
    set(next) {
      phase = next;
      if (!isSettledPhase(next) || waiters.length === 0) return;
      const pending = waiters;
      waiters = [];
      for (const resolve of pending) resolve(next);
    },
    wait() {
      if (isSettledPhase(phase)) return Promise.resolve(phase);
      return new Promise<AuthTokenPhase>((resolve) => {
        waiters.push(resolve);
      });
    },
    peek: () => phase,
    reset() {
      phase = "auth_initializing";
      waiters = [];
    },
  };
}

/**
 * NOTE: there are deliberately no module-level singletons here.
 *
 * An earlier revision of this change exported a process-wide store and gate.
 * That was wrong: every component calling the readiness hook derived its own
 * session identity and epoch, so a late-mounting consumer reset the shared store
 * out from under consumers that had already reached readiness, and instances with
 * differing phases overwrote one another's gate value. Exactly one owner
 * (`TokenReadinessProvider`) instantiates these and publishes the result through
 * context — see `src/contexts/token-readiness.tsx`.
 */
