/**
 * Workspace (WorkOS organization) onboarding state.
 *
 * Checkpoint 24: the backend now auto-maps a verified WorkOS organization to a
 * local Helios organization on first sight, so a tester who signs in WITH an
 * active organization is immediately "ready" — no admin database step. A
 * verified user with NO active organization (the token carries no org_id, so
 * `workos_org_id` is null) still needs a workspace before any org-scoped
 * surface works; the UI shows a bounded "Create your workspace" screen.
 */

import type { UserMe } from "@/lib/api/user";

export type WorkspaceState = "loading" | "ready" | "needs_workspace";

export function deriveWorkspaceState(input: {
  me: UserMe | null;
  loading: boolean;
}): WorkspaceState {
  if (input.loading) return "loading";
  // Unresolved identity (transient error / not authenticated): do not gate —
  // let the normal page flow and the sign-in redirect handle it.
  if (!input.me) return "ready";
  return input.me.organization.workos_org_id ? "ready" : "needs_workspace";
}
