/**
 * Helios auth hooks: WorkOS AuthKit in production/dev, E2E seam in test mode.
 *
 * E2E mode never accepts arbitrary browser-supplied tokens. The client only
 * receives a runtime token from the locked-down `/api/e2e/session` route.
 */

import {
  useAccessToken as useWorkOSAccessToken,
  useAuth as useWorkOSAuth,
} from "@workos/authkit-tanstack-react-start/client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { isE2EClientFlag } from "./e2e-guards";
import {
  clearE2EClientCache,
  getE2EAccessToken,
  getE2EOrganizationId,
  type E2ESessionPayload,
} from "./e2e-session";

type HeliosUser = {
  id: string;
  email: string;
  firstName: string | null;
  lastName: string | null;
};

export interface HeliosAccessToken {
  getAccessToken: () => Promise<string | null>;
  refresh: () => Promise<string | null>;
  /** SDK initial-token loading. NOT sufficient on its own — see token-readiness. */
  loading: boolean;
  /** Whether the SDK currently holds a token. The value itself is never exposed. */
  hasToken: boolean;
  /** Whether the last SDK token operation failed. The error object is not exposed. */
  hasError: boolean;
}

export function useHeliosAccessToken(): HeliosAccessToken {
  const workos = useWorkOSAccessToken();
  const workosRef = useRef(workos);
  workosRef.current = workos;
  const e2e = isE2EClientFlag();

  const getAccessToken = useCallback(async () => {
    if (e2e) {
      return getE2EAccessToken();
    }
    const token = await workosRef.current.getAccessToken();
    return token ?? null;
  }, [e2e]);

  // Force one SDK-managed token refresh (single-flight inside the SDK). In E2E
  // mode the runtime token is fixed, so refresh resolves to the same token.
  const refresh = useCallback(async () => {
    if (e2e) {
      return getE2EAccessToken();
    }
    const token = await workosRef.current.refresh();
    return token ?? null;
  }, [e2e]);

  return {
    getAccessToken,
    refresh,
    // In E2E mode the SDK token store is unused; readiness is driven entirely by
    // the acquisition coordinator against `/api/e2e/session`.
    loading: e2e ? false : workos.loading,
    hasToken: e2e ? false : Boolean(workos.accessToken),
    hasError: e2e ? false : workos.error != null,
  };
}

export function useHeliosAuth(): {
  user: HeliosUser | null;
  organizationId: string | null | undefined;
  loading: boolean;
  signOut: (options?: { returnTo?: string }) => Promise<void> | void;
} {
  const workos = useWorkOSAuth();
  const e2e = isE2EClientFlag();
  const [e2eUser, setE2eUser] = useState<HeliosUser | null>(null);
  const [e2eOrgId, setE2eOrgId] = useState<string | null>(null);
  const [e2eLoading, setE2eLoading] = useState(e2e);

  useEffect(() => {
    if (!e2e) return;
    let cancelled = false;
    async function load() {
      try {
        const response = await fetch("/api/e2e/session", {
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        if (!response.ok) {
          if (!cancelled) {
            setE2eUser(null);
            setE2eOrgId(null);
            setE2eLoading(false);
          }
          return;
        }
        const session = (await response.json()) as E2ESessionPayload;
        if (cancelled) return;
        setE2eUser({
          id: session.user.id,
          email: session.user.email,
          firstName: session.user.firstName,
          lastName: session.user.lastName,
        });
        setE2eOrgId(session.organizationId);
        setE2eLoading(false);
      } catch {
        if (!cancelled) {
          setE2eUser(null);
          setE2eOrgId(null);
          setE2eLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [e2e]);

  const signOutWorkos = workos.signOut;

  return useMemo(() => {
    if (!e2e) {
      return {
        user: workos.user
          ? {
              id: workos.user.id,
              email: workos.user.email,
              firstName: workos.user.firstName ?? null,
              lastName: workos.user.lastName ?? null,
            }
          : null,
        organizationId: workos.organizationId,
        loading: workos.loading,
        signOut: signOutWorkos,
      };
    }
    return {
      user: e2eUser,
      organizationId: e2eOrgId,
      loading: e2eLoading,
      signOut: async () => {
        clearE2EClientCache();
        window.location.href = "/";
      },
    };
  }, [
    e2e,
    workos.user,
    workos.organizationId,
    workos.loading,
    signOutWorkos,
    e2eUser,
    e2eOrgId,
    e2eLoading,
  ]);
}

/** Prefetch helpers for tests / optional warmup. */
export async function warmE2EOrganizationId(): Promise<string | null> {
  return getE2EOrganizationId();
}
