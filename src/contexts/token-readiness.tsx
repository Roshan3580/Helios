/**
 * The single owner of AuthKit access-token readiness (Checkpoint 27).
 *
 * WHY A PROVIDER AND NOT A PLAIN HOOK
 * ----------------------------------
 * Readiness is inherently shared state: one WorkOS session, one initial token
 * acquisition, one recovery decision. Deriving it independently inside every
 * consumer breaks in two ways that this provider structurally prevents:
 *
 * - Session-identity epochs would be per-instance counters. A consumer mounted
 *   later (a route change) starts its own count at 1 and would reset the shared
 *   acquisition state that already-mounted consumers depend on.
 * - Consumers observe AuthKit at slightly different times (in the E2E seam each
 *   instance resolves its own session fetch), so instances would disagree about
 *   the current phase and overwrite each other's readiness gate.
 *
 * With one owner there is exactly one identity, one epoch, one bounded
 * acquisition flight, and one phase — which is also what makes "one SDK token
 * acquisition for N mounted hooks" true rather than merely likely.
 *
 * Nothing here stores, logs, or exposes a token value, cookie, or header.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useSyncExternalStore,
  type ReactNode,
} from "react";

import { useHeliosAccessToken, useHeliosAuth } from "@/lib/auth/helios-auth";
import {
  noteTokenReadiness,
  reportSessionExpired,
  setAuthEpoch,
  useSessionRecovery,
  type SessionRecoveryState,
} from "@/lib/auth/session-recovery";
import {
  createReadinessGate,
  createTokenAcquisitionStore,
  phaseAllowsRequest,
  phaseDiagnostic,
  resolveTokenPhase,
  type AuthDiagnostic,
  type AuthTokenPhase,
} from "@/lib/auth/token-readiness";
import { isE2EClientFlag } from "@/lib/auth/e2e-guards";

export interface TokenReadiness {
  phase: AuthTokenPhase;
  /** A backend request may be issued. Use this as a data-effect dependency. */
  ready: boolean;
  /** Auth or token initialization in progress; show an ordinary loading state. */
  tokenLoading: boolean;
  /** Internal, non-sensitive classification. Never rendered verbatim. */
  diagnostic: AuthDiagnostic | null;
  recovery: SessionRecoveryState;
  getAccessToken: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
  awaitReady: () => Promise<AuthTokenPhase>;
}

const TokenReadinessContext = createContext<TokenReadiness | null>(null);

export function TokenReadinessProvider({ children }: { children: ReactNode }) {
  const e2e = isE2EClientFlag();
  const { user, loading: authLoading } = useHeliosAuth();
  const { getAccessToken, refresh, hasToken } = useHeliosAccessToken();
  const recovery = useSessionRecovery();

  // One acquisition store and one gate for the whole authenticated app.
  const storeRef = useRef<ReturnType<typeof createTokenAcquisitionStore> | null>(null);
  storeRef.current ??= createTokenAcquisitionStore();
  const store = storeRef.current;

  const gateRef = useRef<ReturnType<typeof createReadinessGate> | null>(null);
  gateRef.current ??= createReadinessGate();
  const gate = gateRef.current;

  // Opaque identity used ONLY to detect a session change, so a new session can
  // clear a stale recovery state. Never logged, rendered, or persisted.
  const identity = user ? `${user.id}|${e2e ? "e2e" : ""}` : "";
  const identityRef = useRef<string | null>(null);
  const epochRef = useRef(0);
  if (identityRef.current !== identity) {
    identityRef.current = identity;
    epochRef.current += 1;
  }
  const epoch = epochRef.current;

  // The SDK's token callbacks are referentially stable, so this is idempotent.
  store.configure({ getToken: getAccessToken, refresh });

  const acquisition = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getServerSnapshot,
  );

  const phase = resolveTokenPhase({
    authLoading,
    hasUser: Boolean(user),
    hasToken,
    acquisition: acquisition.state,
  });
  const diagnostic = phaseDiagnostic(phase, acquisition.diagnostic);

  // Discard acquisition state on a session change, and attribute any subsequent
  // failure to this epoch.
  useEffect(() => {
    setAuthEpoch(epoch);
    store.resetForEpoch(epoch);
  }, [epoch, store]);

  // Publish the phase to the imperative `run()` path, from a committed state.
  useEffect(() => {
    gate.set(phase);
  }, [gate, phase]);

  // Drive the bounded acquisition once a user exists but no token does. The
  // store is single-flight, so N mounted hooks share one acquisition.
  useEffect(() => {
    if (phase !== "token_initializing") return;
    void store.acquire();
  }, [phase, epoch, store]);

  // A genuinely new valid token clears a stale recovery state; the same identity
  // that failed stays terminal. Idempotent per epoch — never a per-render reset.
  useEffect(() => {
    if (phase !== "token_ready") return;
    noteTokenReadiness(epoch);
  }, [phase, epoch]);

  // A settled acquisition failure is the ONLY token-side path into recovery.
  useEffect(() => {
    if (phase !== "token_unavailable") return;
    reportSessionExpired(acquisition.diagnostic ?? "token_unavailable");
  }, [phase, acquisition.diagnostic]);

  const awaitReady = useCallback(() => gate.wait(), [gate]);

  // Memoized so consumers (and therefore their data effects) are not re-rendered
  // by unrelated provider renders.
  const value = useMemo<TokenReadiness>(
    () => ({
      phase,
      ready: phaseAllowsRequest(phase),
      tokenLoading: phase === "auth_initializing" || phase === "token_initializing",
      diagnostic,
      recovery,
      getAccessToken,
      refresh,
      awaitReady,
    }),
    [phase, diagnostic, recovery, getAccessToken, refresh, awaitReady],
  );

  return <TokenReadinessContext.Provider value={value}>{children}</TokenReadinessContext.Provider>;
}

export function useTokenReadiness(): TokenReadiness {
  const ctx = useContext(TokenReadinessContext);
  if (!ctx) {
    throw new Error("useTokenReadiness must be used within a TokenReadinessProvider");
  }
  return ctx;
}
