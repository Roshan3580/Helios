import { createFileRoute, redirect } from "@tanstack/react-router";
import { getAuth, getSignInUrl } from "@workos/authkit-tanstack-react-start";

import { AppShell } from "@/components/helios/app-shell";
import { isE2EClientFlag } from "@/lib/auth/e2e-guards";
import { safeReturnPath } from "@/lib/auth/return-path";

export const Route = createFileRoute("/app")({
  // Server-enforced authentication: getAuth is a server function (runs via
  // RPC on client-side navigation), so client React state alone never gates
  // access. Unauthenticated users are sent to AuthKit sign-in with the
  // intended pathname preserved as the post-login return path.
  //
  // E2E mode (Checkpoint 13): when VITE_HELIOS_E2E_TEST_MODE=true, skip WorkOS
  // hosted login so the AppShell can load. This boolean alone never issues a
  // token — API calls still fetch a runtime JWT from the locked-down
  // `/api/e2e/session` route (server-gated; loopback JWKS; non-production).
  // Do not import e2e-session.server here: that would embed server env reads
  // into the client route bundle.
  beforeLoad: async ({ location }) => {
    if (isE2EClientFlag()) {
      return;
    }

    let auth: Awaited<ReturnType<typeof getAuth>>;
    try {
      auth = await getAuth();
    } catch (error) {
      throw new Error(
        "Sign-in is unavailable: WorkOS authentication is not configured on this server. " +
          "Set the WORKOS_* environment variables (see docs/ADR_004_WORKOS_HUMAN_AUTH.md).",
        { cause: error },
      );
    }
    if (!auth.user) {
      const signInUrl = await getSignInUrl({
        data: safeReturnPath(location.pathname),
      });
      throw redirect({ href: signInUrl });
    }
  },
  head: () => ({ meta: [{ title: "Helios: Observatory" }] }),
  component: AppShell,
});
