import { createFileRoute } from "@tanstack/react-router";
import { handleCallbackRoute } from "@workos/authkit-tanstack-react-start";

export const Route = createFileRoute("/api/auth/callback")({
  server: {
    handlers: {
      // Callback failures redirect to a user-facing route with a benign flag;
      // raw provider errors and tokens are never surfaced or logged here.
      GET: handleCallbackRoute({ errorRedirectUrl: "/?auth_error=1" }),
    },
  },
});
