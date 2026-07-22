import { createFileRoute } from "@tanstack/react-router";
import { signOut } from "@workos/authkit-tanstack-react-start";

export const Route = createFileRoute("/api/auth/sign-out")({
  server: {
    handlers: {
      GET: async () => {
        try {
          // signOut terminates the AuthKit session and throws a redirect to
          // the WorkOS logout URL (or the returnTo fallback).
          await signOut({ data: { returnTo: "/" } });
        } catch (thrown) {
          if (thrown instanceof Response) {
            return thrown;
          }
          throw thrown;
        }
        return new Response(null, { status: 302, headers: { Location: "/" } });
      },
    },
  },
});
