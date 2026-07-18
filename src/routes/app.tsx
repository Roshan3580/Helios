import { createFileRoute, redirect } from "@tanstack/react-router";
import { getAuth, getSignInUrl } from "@workos/authkit-tanstack-react-start";

import { AppShell } from "@/components/helios/app-shell";
import { safeReturnPath } from "@/lib/auth/return-path";

export const Route = createFileRoute("/app")({
  // Server-enforced authentication: getAuth is a server function (runs via
  // RPC on client-side navigation), so client React state alone never gates
  // access. Unauthenticated users are sent to AuthKit sign-in with the
  // intended pathname preserved as the post-login return path.
  beforeLoad: async ({ location }) => {
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
