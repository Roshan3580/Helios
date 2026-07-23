import { classifyBackendFailure, COLD_START_MESSAGE } from "@/lib/api/cold-start";

/**
 * Shared error surface for authenticated pages. Distinguishes a Render Free
 * cold start (a sleeping backend that just needs a moment) from a real error,
 * and offers a manual Retry that re-runs the original request. There is no
 * automatic retry loop; the underlying error is always preserved (shown
 * directly for real errors, and in a disclosure during a cold start) so a
 * genuine failure is never hidden behind the waking-up message.
 *
 * 401/403 are handled upstream (sign-in redirect / access message) and are
 * never treated as a cold start here.
 */
export function BackendStateNotice({
  error,
  status,
  onRetry,
}: {
  error: string;
  status: number | null;
  onRetry?: () => void;
}) {
  const coldStart = classifyBackendFailure(status) === "cold_start";
  return (
    <div className="border border-rule bg-paper-2 px-4 py-4" role="alert" aria-live="polite">
      <p className="text-[13px]">{coldStart ? COLD_START_MESSAGE : error}</p>
      {coldStart ? (
        <details className="mt-2 text-[12px] text-muted-foreground">
          <summary className="cursor-pointer">Details</summary>
          <p className="mt-1 break-words">{error}</p>
        </details>
      ) : null}
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 border border-rule px-2.5 py-1.5 text-[12px] hover:bg-paper"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
