/**
 * Free-beta cold-start classification.
 *
 * The invited beta backend runs on a Render Free web service that sleeps after
 * inactivity and can take up to a minute to wake. This helper classifies an
 * authenticated API failure so the UI can distinguish a sleeping/unreachable
 * backend from an authentication problem or a genuine application error.
 *
 * Rules (see Checkpoint 24):
 * - 401/403 are NEVER a cold start — they are authentication/authorization and
 *   are handled by the sign-in redirect or an access message.
 * - 502/503/504 and 408, plus a network-level failure that never reached the
 *   backend (no HTTP status: null/undefined/0), are treated as a cold start.
 * - Any other HTTP status (e.g. 404, 422, 500) is a real error and its message
 *   must be surfaced, never hidden behind the waking-up notice.
 */

export type BackendFailureKind = "cold_start" | "auth" | "error";

export const COLD_START_MESSAGE = "Helios Beta is waking up. This can take up to a minute.";

export function classifyBackendFailure(status: number | null | undefined): BackendFailureKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 502 || status === 503 || status === 504 || status === 408) {
    return "cold_start";
  }
  // No HTTP response reached the client (network error / connection refused /
  // client abort): the free instance is most likely asleep or still waking.
  if (status === null || status === undefined || status === 0) return "cold_start";
  return "error";
}

export function isColdStart(status: number | null | undefined): boolean {
  return classifyBackendFailure(status) === "cold_start";
}
