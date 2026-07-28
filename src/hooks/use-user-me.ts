import { useEffect, useState } from "react";

import { useAuthorizedRequest } from "@/lib/api/authorized-request";
import { fetchUserMe, type UserMe } from "@/lib/api/user";

export interface UserMeState {
  me: UserMe | null;
  loading: boolean;
  error: string | null;
}

/**
 * Loads /v2/user/me with a fresh WorkOS access token.
 *
 * Checkpoint 27: this effect used to run once on mount with an empty dependency
 * list. Because AuthKit resolves the user in its own mount effect — which React
 * runs *after* this child effect — the token was still unavailable and the
 * request was never issued, while the empty dependency list meant the hook could
 * never retry. It now waits for token readiness and re-runs when readiness
 * changes, so a valid session always produces exactly one profile request.
 */
export function useUserMe(): UserMeState {
  const { run, ready, phase } = useAuthorizedRequest();
  const [state, setState] = useState<UserMeState>({ me: null, loading: true, error: null });

  useEffect(() => {
    if (!ready) {
      // auth_initializing / token_initializing: ordinary bounded loading, no
      // request and no expiry. A settled failure has already been reported to
      // central session recovery, which renders in place of the route.
      if (phase === "token_unavailable" || phase === "unauthenticated") {
        setState({ me: null, loading: false, error: null });
      } else {
        setState({ me: null, loading: true, error: null });
      }
      return;
    }

    let cancelled = false;

    async function load() {
      try {
        const me = await run((token) => fetchUserMe(token));
        if (!cancelled) setState({ me, loading: false, error: null });
      } catch (error) {
        if (!cancelled) {
          setState({
            me: null,
            loading: false,
            error: error instanceof Error ? error.message : "failed to load profile",
          });
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [ready, phase, run]);

  return state;
}
