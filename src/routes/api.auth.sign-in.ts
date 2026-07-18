import { createFileRoute } from "@tanstack/react-router";
import { getSignInUrl } from "@workos/authkit-tanstack-react-start";

import { safeReturnPath } from "@/lib/auth/return-path";

export const Route = createFileRoute("/api/auth/sign-in")({
  server: {
    handlers: {
      GET: async ({ request }) => {
        const url = new URL(request.url);
        const returnPath = safeReturnPath(url.searchParams.get("return"));
        const signInUrl = await getSignInUrl({ data: returnPath });
        return new Response(null, { status: 302, headers: { Location: signInUrl } });
      },
    },
  },
});
