import { createFileRoute, Link } from "@tanstack/react-router";

import { PageHeader } from "@/components/helios/app-shell";
import { BackendStateNotice } from "@/components/helios/backend-state-notice";
import { ProjectApiKeysPanel } from "@/components/helios/project-api-keys-panel";
import { useProjectSelection } from "@/contexts/project-selection";

export const Route = createFileRoute("/app/settings/api-keys")({
  component: ProjectApiKeysSettingsPage,
});

function ProjectApiKeysSettingsPage() {
  const { selectedProject, loading, error, errorStatus, reload } = useProjectSelection();

  return (
    <div>
      <PageHeader
        eyebrow="Setup"
        title="Project API keys"
        description="Create, list, and revoke machine credentials for the selected project. Plaintext is shown once at creation."
      />

      {error ? (
        <BackendStateNotice error={error} status={errorStatus} onRetry={reload} />
      ) : loading ? (
        <p className="text-[13px] text-muted-foreground" aria-busy="true">
          Loading project…
        </p>
      ) : !selectedProject ? (
        <div className="border border-rule px-4 py-4">
          <p className="text-[13px] text-muted-foreground">
            No project selected. Create a project to manage API keys.
          </p>
          <Link
            to="/app/getting-started"
            className="mt-3 inline-block border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper"
          >
            Getting started
          </Link>
        </div>
      ) : (
        <ProjectApiKeysPanel
          projectId={selectedProject.id}
          projectName={selectedProject.name}
          projectSlug={selectedProject.slug}
        />
      )}
    </div>
  );
}
