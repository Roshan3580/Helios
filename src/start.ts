import { createStart, createMiddleware, createCsrfMiddleware } from "@tanstack/react-start";
import { authkitMiddleware } from "@workos/authkit-tanstack-react-start";

import { renderErrorPage } from "./lib/error-page";

// Defining a custom startInstance disables TanStack Start's automatic CSRF
// protection, so it is re-added explicitly here (framework-recommended filter:
// protect server-function RPC endpoints).
const csrfMiddleware = createCsrfMiddleware({
  filter: (ctx) => ctx.handlerType === "serverFn",
});

const errorMiddleware = createMiddleware().server(async ({ next }) => {
  try {
    return await next();
  } catch (error) {
    if (error != null && typeof error === "object" && "statusCode" in error) {
      throw error;
    }
    // Redirects thrown by auth flows must pass through untouched.
    if (error instanceof Response) {
      return error;
    }
    console.error(error);
    return new Response(renderErrorPage(), {
      status: 500,
      headers: { "content-type": "text/html; charset=utf-8" },
    });
  }
});

// AuthKit reads server-only WORKOS_* env vars at request time. The middleware
// is attached only when WorkOS is configured so that builds, CI, and the
// public demo keep working without credentials; auth routes then fail with a
// clear error instead of breaking every request. Order: CSRF first, then the
// error boundary (so auth failures render the error page), then AuthKit.
const workosConfigured = Boolean(process.env.WORKOS_CLIENT_ID);

export const startInstance = createStart(() => ({
  requestMiddleware: [
    csrfMiddleware,
    errorMiddleware,
    ...(workosConfigured ? [authkitMiddleware()] : []),
  ],
}));
