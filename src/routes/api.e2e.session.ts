import { createFileRoute } from "@tanstack/react-router";

import { e2eAccessDeniedReason, getE2ESessionOrNull } from "@/lib/auth/e2e-session.server";

/**
 * Test-only session bootstrap.
 *
 * Returns 404 unless HELIOS_E2E_TEST_MODE is explicitly enabled under a
 * non-production Node environment with a loopback JWKS/issuer and a
 * runtime-minted access token in server env. Never accepts client-supplied
 * tokens in the request body or query string.
 */
export const Route = createFileRoute("/api/e2e/session")({
  server: {
    handlers: {
      GET: async () => {
        const session = getE2ESessionOrNull();
        if (!session) {
          const reason = e2eAccessDeniedReason() ?? "e2e_auth_unavailable";
          return Response.json({ error: "not_found", reason }, { status: 404 });
        }
        return Response.json(session, {
          headers: {
            "Cache-Control": "no-store",
          },
        });
      },
      POST: async () => Response.json({ error: "method_not_allowed" }, { status: 405 }),
    },
  },
});
