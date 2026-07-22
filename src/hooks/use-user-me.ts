import { useEffect, useState } from "react";
import { useHeliosAccessToken as useAccessToken } from "@/lib/auth/helios-auth";

import { fetchUserMe, type UserMe } from "@/lib/api/user";

export interface UserMeState {
  me: UserMe | null;
  loading: boolean;
  error: string | null;
}

/**
 * Loads /v2/user/me with a fresh WorkOS access token obtained immediately
 * before the call (getAccessToken auto-refreshes; nothing is cached manually
 * and the token is never persisted).
 */
export function useUserMe(): UserMeState {
  const { getAccessToken } = useAccessToken();
  const [state, setState] = useState<UserMeState>({ me: null, loading: true, error: null });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const token = await getAccessToken();
        if (!token) {
          if (!cancelled) setState({ me: null, loading: false, error: "not authenticated" });
          return;
        }
        const me = await fetchUserMe(token);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}
