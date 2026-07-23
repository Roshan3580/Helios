import { PageHeader } from "@/components/helios/app-shell";

/**
 * Bounded "Create your workspace" onboarding for a verified user who is not yet
 * a member of any workspace (WorkOS organization), so no org-scoped surface can
 * work for them yet.
 *
 * Scope note (Checkpoint 24): programmatic in-app WorkOS organization creation
 * is intentionally NOT enabled in this build. The committed AuthKit integration
 * exposes session/sign-in helpers and organization switching, but no public
 * organization-creation API; creating an organization would require the WorkOS
 * management SDK and a server-side WORKOS_API_KEY, which is a separate, larger,
 * and independently verifiable change. Rather than weaken authentication or
 * invent a custom flow, this screen explains the supported paths (accept a
 * WorkOS invitation, or create an organization during WorkOS hosted sign-up)
 * and re-enters the standard sign-in route. Once the session carries an
 * organization, the backend maps it to a local workspace automatically — no
 * administrator database step is required.
 */
export function WorkspaceOnboarding() {
  return (
    <div>
      <PageHeader
        eyebrow="Setup"
        title="Create your workspace"
        description="You're signed in, but your account isn't part of a Helios workspace yet. A workspace groups your projects, telemetry, and API keys."
      />
      <div className="max-w-xl space-y-4 border border-rule bg-paper px-4 py-5 text-[13px]">
        <p>To start using Helios Beta, join or create a workspace:</p>
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>
            <span className="text-foreground">Invited by a teammate?</span> Accept the workspace
            invitation from WorkOS, then sign in again — Helios links your workspace automatically.
          </li>
          <li>
            <span className="text-foreground">Setting up a new team?</span> Create your organization
            during WorkOS sign-in, then return here.
          </li>
        </ul>
        <div className="flex flex-wrap gap-2 pt-1">
          <a
            href="/api/auth/sign-in?return=/app/getting-started"
            className="border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper"
          >
            Continue to sign-in
          </a>
        </div>
        <p className="border-t border-rule pt-3 text-[12px] text-muted-foreground">
          Beta note: workspaces are provisioned through WorkOS (invitation or hosted sign-up).
          In-app workspace creation is not enabled in this build. Once your session includes a
          workspace, no administrator database step is needed — mapping is automatic and
          tenant-isolated.
        </p>
      </div>
    </div>
  );
}
