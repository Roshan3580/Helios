/**
 * Checkpoint 27 regression tests: AuthKit access-token readiness.
 *
 * These model the ACTUAL hosted failure shape. The installed WorkOS SDK
 * (@workos/authkit-tanstack-react-start 0.11.0) behaves as follows, and the fakes
 * below reproduce it exactly:
 *
 * - `AuthKitProvider` mounts with `user: null, loading: true` when no
 *   `initialAuth` is supplied, and resolves the user in its OWN mount effect.
 * - React runs child effects before parent effects, so a data hook under the
 *   provider runs before the provider has asked who the user is.
 * - `useAccessToken().getAccessToken()` returns `undefined` IMMEDIATELY when the
 *   user is null — it never contacts WorkOS, which is why the hosted backend saw
 *   no request at all during the failure.
 * - `useAccessToken().loading` is `false` during that window (its initial value
 *   is `Boolean(user && …)`), so SDK token `loading` alone is not a valid gate.
 * - There is also a committed render where the user is valid, `loading` is
 *   `false`, and no token exists yet.
 *
 * Only fake users and fake tokens appear here. No real hosted JWT is decoded and
 * no token value is ever logged.
 */

import { afterEach, beforeEach, describe, expect, test } from "bun:test";

import {
  createReadinessGate,
  createTokenAcquisitionStore,
  isSettledPhase,
  phaseAllowsRequest,
  phaseDiagnostic,
  resolveTokenPhase,
  type AuthTokenPhase,
} from "./token-readiness";
import {
  getSessionRecoverySnapshot,
  noteTokenReadiness,
  reportRateLimited,
  reportSessionExpired,
  resetSessionRecovery,
  setAuthEpoch,
} from "./session-recovery";

const FAKE_TOKEN = "fake.access.token";

beforeEach(() => {
  resetSessionRecovery();
});
afterEach(() => {
  resetSessionRecovery();
});

// ---------------------------------------------------------------------------
// Phase resolution: the contract itself
// ---------------------------------------------------------------------------

describe("resolveTokenPhase", () => {
  const base = { authLoading: false, hasUser: true, hasToken: false, acquisition: "idle" } as const;

  test("A: auth loading dominates, even though SDK token loading reports false", () => {
    // This is the exact hosted mount state: provider loading, user not yet known,
    // and the SDK token hook reporting loading:false with no token.
    expect(resolveTokenPhase({ ...base, authLoading: true, hasUser: false })).toBe(
      "auth_initializing",
    );
    expect(resolveTokenPhase({ ...base, authLoading: true, hasUser: true })).toBe(
      "auth_initializing",
    );
  });

  test("B: authenticated with a pending acquisition is token_initializing", () => {
    expect(resolveTokenPhase({ ...base, acquisition: "pending" })).toBe("token_initializing");
  });

  test("B: authenticated, no token, no acquisition yet is token_initializing, never terminal", () => {
    // The committed render between the auth RPC resolving and the SDK's own token
    // effect running. Classifying this as unavailable reproduces the defect.
    expect(resolveTokenPhase({ ...base, acquisition: "idle" })).toBe("token_initializing");
  });

  test("C: a present SDK token is ready", () => {
    expect(resolveTokenPhase({ ...base, hasToken: true })).toBe("token_ready");
  });

  test("C: a successful acquisition is ready even without SDK token state (E2E seam)", () => {
    expect(resolveTokenPhase({ ...base, acquisition: "ready" })).toBe("token_ready");
  });

  test("D: only a settled acquisition failure is terminal", () => {
    expect(resolveTokenPhase({ ...base, acquisition: "failed" })).toBe("token_unavailable");
  });

  test("E: no user after auth loading completes is a sign-in boundary", () => {
    expect(resolveTokenPhase({ ...base, hasUser: false })).toBe("unauthenticated");
  });

  test("only token_ready permits a backend request", () => {
    const phases: AuthTokenPhase[] = [
      "auth_initializing",
      "token_initializing",
      "token_ready",
      "token_unavailable",
      "unauthenticated",
    ];
    expect(phases.filter(phaseAllowsRequest)).toEqual(["token_ready"]);
  });

  test("initializing phases are never settled; failures and readiness are", () => {
    expect(isSettledPhase("auth_initializing")).toBe(false);
    expect(isSettledPhase("token_initializing")).toBe(false);
    expect(isSettledPhase("token_ready")).toBe(true);
    expect(isSettledPhase("token_unavailable")).toBe(true);
    expect(isSettledPhase("unauthenticated")).toBe(true);
  });

  test("diagnostics carry no sensitive material", () => {
    expect(phaseDiagnostic("auth_initializing", null)).toBe("auth_initializing");
    expect(phaseDiagnostic("token_initializing", null)).toBe("token_initializing");
    expect(phaseDiagnostic("token_unavailable", "token_refresh_failed")).toBe(
      "token_refresh_failed",
    );
    expect(phaseDiagnostic("token_unavailable", null)).toBe("token_unavailable");
    expect(phaseDiagnostic("token_ready", null)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Bounded, single-flight acquisition
// ---------------------------------------------------------------------------

describe("token acquisition (bounded, single-flight)", () => {
  test("a token from getToken settles ready without any refresh", async () => {
    let refreshes = 0;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => FAKE_TOKEN,
      refresh: async () => {
        refreshes += 1;
        return FAKE_TOKEN;
      },
    });
    expect(await store.acquire()).toEqual({ state: "ready", diagnostic: null });
    expect(refreshes).toBe(0);
    expect(store.getSnapshot().state).toBe("ready");
  });

  test("no token then a successful refresh settles ready (bounded refresh once)", async () => {
    let gets = 0;
    let refreshes = 0;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => {
        gets += 1;
        return null;
      },
      refresh: async () => {
        refreshes += 1;
        return FAKE_TOKEN;
      },
    });
    expect(await store.acquire()).toEqual({ state: "ready", diagnostic: null });
    expect(gets).toBe(1);
    expect(refreshes).toBe(1);
  });

  test("no token after one refresh settles token_unavailable and does not retry", async () => {
    let refreshes = 0;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => null,
      refresh: async () => {
        refreshes += 1;
        return null;
      },
    });
    expect(await store.acquire()).toEqual({ state: "failed", diagnostic: "token_unavailable" });
    // Bounded: repeated calls never launch another flight.
    expect(await store.acquire()).toEqual({ state: "failed", diagnostic: "token_unavailable" });
    expect(await store.acquire()).toEqual({ state: "failed", diagnostic: "token_unavailable" });
    expect(refreshes).toBe(1);
  });

  test("a rejecting token server function is classified, not logged", async () => {
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => {
        throw new Error("server function failed");
      },
      refresh: async () => FAKE_TOKEN,
    });
    const result = await store.acquire();
    expect(result).toEqual({ state: "failed", diagnostic: "token_server_action_failed" });
    // The classification is a constant string; the error object never escapes.
    expect(typeof result.diagnostic).toBe("string");
  });

  test("a rejecting refresh is classified separately", async () => {
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => null,
      refresh: async () => {
        throw new Error("refresh failed");
      },
    });
    expect(await store.acquire()).toEqual({
      state: "failed",
      diagnostic: "token_refresh_failed",
    });
  });

  test("concurrent consumers share exactly one acquisition flight", async () => {
    let gets = 0;
    let release: ((token: string | null) => void) | null = null;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: () => {
        gets += 1;
        return new Promise((resolve) => {
          release = resolve;
        });
      },
      refresh: async () => null,
    });

    // Eight authenticated hooks mount during token initialization.
    const flights = Array.from({ length: 8 }, () => store.acquire());
    expect(store.getSnapshot().state).toBe("pending");
    release!(FAKE_TOKEN);
    const results = await Promise.all(flights);

    expect(gets).toBe(1); // one SDK token acquisition, not eight
    for (const result of results) expect(result).toEqual({ state: "ready", diagnostic: null });
  });

  test("a settled ready state is reused without a new flight", async () => {
    let gets = 0;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => {
        gets += 1;
        return FAKE_TOKEN;
      },
      refresh: async () => null,
    });
    await store.acquire();
    await store.acquire();
    await store.acquire();
    expect(gets).toBe(1);
  });

  test("a session change resets state so a new epoch can acquire again", async () => {
    let gets = 0;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: async () => {
        gets += 1;
        return null;
      },
      refresh: async () => null,
    });
    expect((await store.acquire()).state).toBe("failed");
    store.resetForEpoch(1);
    expect(store.getSnapshot().state).toBe("idle");
    expect((await store.acquire()).state).toBe("failed");
    expect(gets).toBe(2);
  });

  test("a flight from a superseded epoch never overwrites newer state", async () => {
    let release: ((token: string | null) => void) | null = null;
    const store = createTokenAcquisitionStore();
    store.configure({
      getToken: () =>
        new Promise((resolve) => {
          release = resolve;
        }),
      refresh: async () => null,
    });
    const stale = store.acquire();
    store.resetForEpoch(7); // session changed while the flight was open
    release!(null);
    await stale;
    expect(store.getSnapshot().state).toBe("idle");
  });
});

// ---------------------------------------------------------------------------
// Readiness gate: `run()` waits instead of misclassifying initialization
// ---------------------------------------------------------------------------

describe("readiness gate", () => {
  test("waiters block on initializing phases and resolve on the settled phase", async () => {
    const gate = createReadinessGate();
    let resolved: AuthTokenPhase | null = null;
    const waiting = gate.wait().then((phase) => {
      resolved = phase;
      return phase;
    });

    gate.set("auth_initializing");
    gate.set("token_initializing");
    await Promise.resolve();
    expect(resolved).toBeNull(); // still waiting — no timer involved

    gate.set("token_ready");
    expect(await waiting).toBe("token_ready");
  });

  test("an already-settled gate resolves immediately", async () => {
    const gate = createReadinessGate();
    gate.set("token_ready");
    expect(await gate.wait()).toBe("token_ready");
  });

  test("a settled failure resolves waiters rather than hanging", async () => {
    const gate = createReadinessGate();
    const waiting = gate.wait();
    gate.set("token_unavailable");
    expect(await waiting).toBe("token_unavailable");
  });
});

// ---------------------------------------------------------------------------
// Session-recovery epoch semantics
// ---------------------------------------------------------------------------

describe("recovery state across session epochs", () => {
  test("readiness for a NEW epoch clears a pre-auth transient expiry", () => {
    // Epoch 0 is the pre-auth window where the defect fired.
    setAuthEpoch(0);
    reportSessionExpired("token_unavailable");
    expect(getSessionRecoverySnapshot().status).toBe("expired");

    // The user then hydrates and a real token arrives: a genuinely new identity.
    noteTokenReadiness(1);
    expect(getSessionRecoverySnapshot().status).toBe("active");
    expect(getSessionRecoverySnapshot().reason).toBeNull();
  });

  test("readiness for the SAME epoch that failed stays terminal", () => {
    setAuthEpoch(3);
    reportSessionExpired("backend_unauthorized");
    noteTokenReadiness(3);
    expect(getSessionRecoverySnapshot().status).toBe("expired");
    expect(getSessionRecoverySnapshot().reason).toBe("backend_unauthorized");
  });

  test("repeated readiness for one epoch never resets recovery again", () => {
    setAuthEpoch(1);
    noteTokenReadiness(2); // new epoch, nothing to clear
    reportSessionExpired("backend_unauthorized"); // genuine failure at epoch 2
    // A re-render loop calling readiness repeatedly must not clear it.
    for (let i = 0; i < 50; i += 1) noteTokenReadiness(2);
    expect(getSessionRecoverySnapshot().status).toBe("expired");
  });

  test("a provider rate-limit is never cleared by token readiness", () => {
    setAuthEpoch(0);
    reportSessionExpired("token_unavailable");
    resetSessionRecovery();
    setAuthEpoch(0);
    // Rate limit takes precedence and must survive a readiness transition.
    reportRateLimited(30);
    noteTokenReadiness(9);
    const snapshot = getSessionRecoverySnapshot();
    expect(snapshot.status).toBe("rate_limited");
    expect(snapshot.retryAfterSeconds).toBe(30);
  });
});

// ---------------------------------------------------------------------------
// End-to-end mount simulation of the hosted failure shape
// ---------------------------------------------------------------------------

interface SdkTimelineState {
  authLoading: boolean;
  hasUser: boolean;
  hasToken: boolean;
}

/**
 * Faithful, DOM-free model of the mount lifecycle.
 *
 * Each `commit()` reproduces one React commit: resolve the phase from AuthKit
 * state plus the acquisition snapshot, run the readiness effects, then let
 * microtasks flush and re-commit until the phase stops changing — exactly what a
 * `useSyncExternalStore` update does. Gated consumers are only allowed to issue a
 * backend request when `phaseAllowsRequest(phase)`.
 */
function createShellSimulation(sdk: {
  getToken: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
}) {
  const store = createTokenAcquisitionStore();
  const gate = createReadinessGate();
  store.configure(sdk);

  const backendCalls: string[] = [];
  const expiries: string[] = [];
  let state: SdkTimelineState = { authLoading: true, hasUser: false, hasToken: false };
  let epoch = 0;
  let phase: AuthTokenPhase = "auth_initializing";

  // Consumers modelled on useUserMe / ProjectSelectionProvider: each runs at most
  // once per readiness transition and reports its own loading state.
  const consumers = new Map<
    string,
    { runs: number; loading: boolean; ranAtPhase: string | null }
  >();
  // Mirrors the real effect's dependency list `[phase, acquisition.diagnostic]`:
  // React re-runs it only when those change.
  let lastExpiryDeps: string | null = null;

  function addConsumer(name: string) {
    consumers.set(name, { runs: 0, loading: true, ranAtPhase: null });
  }

  function runEffects(): void {
    // Effect: publish phase for the imperative run() path.
    gate.set(phase);
    // Effect: drive the bounded acquisition while initializing.
    if (phase === "token_initializing") void store.acquire();
    // Effect: a genuinely new valid token clears stale recovery.
    if (phase === "token_ready") noteTokenReadiness(epoch);
    // Effect: only a settled failure reports recovery.
    if (phase === "token_unavailable") {
      const diagnostic = store.getSnapshot().diagnostic ?? "token_unavailable";
      const depsKey = `${phase}|${diagnostic}`;
      if (depsKey !== lastExpiryDeps) {
        lastExpiryDeps = depsKey;
        expiries.push(diagnostic);
        reportSessionExpired(diagnostic);
      }
    } else {
      lastExpiryDeps = null;
    }
    // Gated data effects.
    for (const [name, consumer] of consumers) {
      if (!phaseAllowsRequest(phase)) {
        consumer.loading = phase === "auth_initializing" || phase === "token_initializing";
        continue;
      }
      if (consumer.ranAtPhase === `${epoch}`) continue;
      consumer.ranAtPhase = `${epoch}`;
      consumer.runs += 1;
      consumer.loading = false;
      backendCalls.push(name);
    }
  }

  async function commit(next?: Partial<SdkTimelineState>): Promise<void> {
    if (next) state = { ...state, ...next };
    for (let i = 0; i < 20; i += 1) {
      const resolved = resolveTokenPhase({
        authLoading: state.authLoading,
        hasUser: state.hasUser,
        hasToken: state.hasToken,
        acquisition: store.getSnapshot().state,
      });
      phase = resolved;
      runEffects();
      // Flush microtasks so an acquisition flight can settle and re-render.
      await Promise.resolve();
      await Promise.resolve();
      await Promise.resolve();
      const after = resolveTokenPhase({
        authLoading: state.authLoading,
        hasUser: state.hasUser,
        hasToken: state.hasToken,
        acquisition: store.getSnapshot().state,
      });
      if (after === resolved) break;
    }
  }

  function newSession(): void {
    epoch += 1;
    setAuthEpoch(epoch);
    store.resetForEpoch(epoch);
  }

  return {
    addConsumer,
    commit,
    newSession,
    backendCalls,
    expiries,
    consumers,
    get phase() {
      return phase;
    },
  };
}

/** The installed SDK's real behavior: no user means no token and no RPC at all. */
function createFakeSdk(options: {
  userPresent: () => boolean;
  tokenAvailable?: () => boolean;
  rejectGetToken?: boolean;
  rejectRefresh?: boolean;
}) {
  const counters = { getToken: 0, refresh: 0, rpc: 0 };
  return {
    counters,
    getToken: async (): Promise<string | null> => {
      counters.getToken += 1;
      // Mirrors useAccessToken: short-circuits BEFORE contacting WorkOS.
      if (!options.userPresent()) return null;
      counters.rpc += 1;
      if (options.rejectGetToken) throw new Error("token server function failed");
      return options.tokenAvailable?.() === false ? null : FAKE_TOKEN;
    },
    refresh: async (): Promise<string | null> => {
      counters.refresh += 1;
      if (!options.userPresent()) return null;
      counters.rpc += 1;
      if (options.rejectRefresh) throw new Error("refresh failed");
      return options.tokenAvailable?.() === false ? null : FAKE_TOKEN;
    },
  };
}

describe("hosted mount sequence", () => {
  test("§9.1-4: initialization issues no request and no expiry; readiness then loads", async () => {
    let userPresent = false;
    const sdk = createFakeSdk({ userPresent: () => userPresent });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");
    shell.addConsumer("/v2/user/projects");

    // 1. Mount: AuthKit loading, user unknown. This is where the defect fired.
    await shell.commit({ authLoading: true, hasUser: false, hasToken: false });
    expect(shell.phase).toBe("auth_initializing");
    expect(shell.backendCalls).toEqual([]);
    expect(shell.expiries).toEqual([]);
    expect(getSessionRecoverySnapshot().status).toBe("active");
    // The SDK was never even asked for a token, so no WorkOS RPC occurred.
    expect(sdk.counters.rpc).toBe(0);

    // 2. The auth RPC resolves: valid user, still no token, SDK loading false.
    userPresent = true;
    await shell.commit({ authLoading: false, hasUser: true, hasToken: false });
    expect(shell.backendCalls).toEqual(["/v2/user/me", "/v2/user/projects"]);
    expect(shell.expiries).toEqual([]);
    expect(getSessionRecoverySnapshot().status).toBe("active");
  });

  test("§9.3: a transient no-token result while loading never reports expiry", async () => {
    let userPresent = false;
    const sdk = createFakeSdk({ userPresent: () => userPresent });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");

    // Several commits pass with no user: repeated no-token results.
    await shell.commit({ authLoading: true, hasUser: false });
    await shell.commit({ authLoading: true, hasUser: false });
    await shell.commit({ authLoading: true, hasUser: false });
    expect(getSessionRecoverySnapshot().status).toBe("active");
    expect(shell.backendCalls).toEqual([]);

    userPresent = true;
    await shell.commit({ authLoading: false, hasUser: true });
    expect(getSessionRecoverySnapshot().status).toBe("active");
  });

  test("§9.5: the profile consumer waits and then loads — never permanently stuck", async () => {
    let userPresent = false;
    const sdk = createFakeSdk({ userPresent: () => userPresent });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");

    await shell.commit({ authLoading: true, hasUser: false });
    expect(shell.consumers.get("/v2/user/me")!.runs).toBe(0);
    expect(shell.consumers.get("/v2/user/me")!.loading).toBe(true);

    userPresent = true;
    await shell.commit({ authLoading: false, hasUser: true });
    const consumer = shell.consumers.get("/v2/user/me")!;
    expect(consumer.runs).toBe(1);
    expect(consumer.loading).toBe(false);
  });

  test("§9.6: many hooks mounting during init share one flight and no duplicate calls", async () => {
    let userPresent = false;
    const sdk = createFakeSdk({ userPresent: () => userPresent });
    const shell = createShellSimulation(sdk);
    const names = ["me", "projects", "dashboard", "traces", "api-keys"];
    for (const name of names) shell.addConsumer(name);

    await shell.commit({ authLoading: true, hasUser: false });
    expect(shell.backendCalls).toEqual([]);

    userPresent = true;
    await shell.commit({ authLoading: false, hasUser: true });
    // Exactly one token acquisition RPC despite five consumers.
    expect(sdk.counters.rpc).toBe(1);
    expect(shell.backendCalls).toEqual(names);

    // Extra commits must not re-issue anything.
    await shell.commit();
    await shell.commit();
    expect(shell.backendCalls).toEqual(names);
    for (const name of names) expect(shell.consumers.get(name)!.runs).toBe(1);
  });

  test("§9.7: loading completes but the token stays unavailable → one refresh, then recovery", async () => {
    const sdk = createFakeSdk({ userPresent: () => true, tokenAvailable: () => false });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");

    await shell.commit({ authLoading: false, hasUser: true, hasToken: false });

    expect(shell.phase).toBe("token_unavailable");
    expect(sdk.counters.getToken).toBe(1);
    expect(sdk.counters.refresh).toBe(1); // bounded: exactly one refresh
    expect(shell.backendCalls).toEqual([]); // §9.15: never a request without a token
    expect(getSessionRecoverySnapshot().status).toBe("expired");
    expect(getSessionRecoverySnapshot().reason).toBe("token_unavailable");

    // Stable: further commits neither retry nor flip state.
    await shell.commit();
    await shell.commit();
    expect(sdk.counters.refresh).toBe(1);
    expect(shell.expiries.every((d) => d === "token_unavailable")).toBe(true);
  });

  test("§9.8: a rejecting token server function ends in safe bounded recovery", async () => {
    const sdk = createFakeSdk({ userPresent: () => true, rejectGetToken: true });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");

    await shell.commit({ authLoading: false, hasUser: true, hasToken: false });

    expect(shell.phase).toBe("token_unavailable");
    expect(getSessionRecoverySnapshot().status).toBe("expired");
    // Classified, not leaked: a constant string with no error detail.
    expect(getSessionRecoverySnapshot().reason).toBe("token_server_action_failed");
    expect(shell.backendCalls).toEqual([]);
    // No redirect loop: recovery flips once and only the explicit button navigates.
    await shell.commit();
    await shell.commit();
    expect(shell.expiries).toEqual(["token_server_action_failed"]);
  });

  test("§9.8: a rejecting refresh is classified as token_refresh_failed", async () => {
    const sdk = createFakeSdk({
      userPresent: () => true,
      tokenAvailable: () => false,
      rejectRefresh: true,
    });
    const shell = createShellSimulation(sdk);
    await shell.commit({ authLoading: false, hasUser: true, hasToken: false });
    expect(getSessionRecoverySnapshot().reason).toBe("token_refresh_failed");
  });

  test("§9.14: recovery returns to active only on a genuinely new readiness transition", async () => {
    let tokenAvailable = false;
    const sdk = createFakeSdk({
      userPresent: () => true,
      tokenAvailable: () => tokenAvailable,
    });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");

    await shell.commit({ authLoading: false, hasUser: true, hasToken: false });
    expect(getSessionRecoverySnapshot().status).toBe("expired");

    // Same session, repeated commits: stays terminal.
    await shell.commit();
    await shell.commit();
    expect(getSessionRecoverySnapshot().status).toBe("expired");

    // A genuinely new session/token identity arrives.
    tokenAvailable = true;
    shell.newSession();
    await shell.commit({ authLoading: false, hasUser: true, hasToken: false });
    expect(shell.phase).toBe("token_ready");
    expect(getSessionRecoverySnapshot().status).toBe("active");
    expect(shell.backendCalls).toEqual(["/v2/user/me"]);
  });

  test("§9.15: an unauthenticated session is a sign-in boundary, not a backend 401", async () => {
    const sdk = createFakeSdk({ userPresent: () => false });
    const shell = createShellSimulation(sdk);
    shell.addConsumer("/v2/user/me");

    await shell.commit({ authLoading: false, hasUser: false, hasToken: false });
    expect(shell.phase).toBe("unauthenticated");
    expect(shell.backendCalls).toEqual([]);
    // Not fabricated as expiry: recovery stays active, the route redirect owns it.
    expect(getSessionRecoverySnapshot().status).toBe("active");
    expect(sdk.counters.rpc).toBe(0);
  });
});
