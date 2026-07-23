import { PageHeader } from "@/components/helios/app-shell";
import { beginSignIn, type SessionRecoveryState } from "@/lib/auth/session-recovery";

/**
 * Single, stable authentication-recovery surface for the app shell.
 *
 * Rendered in place of the route content when a bounded authenticated failure
 * has occurred. There is no automatic redirect: only the explicit "Sign in
 * again" button starts a new WorkOS authorization flow (and it is single-flight
 * in `beginSignIn`). A provider rate-limit is shown as a wait message and never
 * triggers a redirect or retry.
 */
export function SessionRecoveryPanel({ state }: { state: SessionRecoveryState }) {
  if (state.status === "rate_limited") {
    return (
      <div>
        <PageHeader
          eyebrow="Session"
          title="Sign-in temporarily unavailable"
          description="Too many sign-in attempts were made in a short window."
        />
        <div
          className="max-w-xl border border-rule bg-paper-2 px-4 py-5 text-[13px]"
          role="alert"
          aria-live="polite"
        >
          <p>Sign-in is temporarily rate-limited. Please wait before trying again.</p>
          {state.retryAfterSeconds != null ? (
            <p className="mt-2 text-[12px] text-muted-foreground">
              You can try again in about {state.retryAfterSeconds} second
              {state.retryAfterSeconds === 1 ? "" : "s"}.
            </p>
          ) : null}
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Session"
        title="Your session has expired"
        description="For your security, sign in again to continue."
      />
      <div
        className="max-w-xl border border-rule bg-paper-2 px-4 py-5 text-[13px]"
        role="alert"
        aria-live="polite"
      >
        <p>Your session has expired. You have not been signed out of WorkOS.</p>
        <button
          type="button"
          onClick={() => beginSignIn()}
          className="mt-3 border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper"
        >
          Sign in again
        </button>
      </div>
    </div>
  );
}
