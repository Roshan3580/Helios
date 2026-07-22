import { safeReturnPath } from "./return-path";

/**
 * Client-side redirect to the AuthKit sign-in route after a 401 from FastAPI.
 * Preserves a safe return path and avoids loops on auth routes themselves.
 */
export function redirectToSignIn(returnPath?: string): void {
  if (typeof window === "undefined") return;
  const current = window.location.pathname;
  if (current.startsWith("/api/auth/")) return;

  const path = safeReturnPath(returnPath ?? current + window.location.search);
  window.location.assign(`/api/auth/sign-in?return=${encodeURIComponent(path)}`);
}
