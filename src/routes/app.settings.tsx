import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";

import { PageHeader } from "@/components/helios/app-shell";
import { Eyebrow } from "@/components/helios/primitives";
import { useProjectSelection } from "@/contexts/project-selection";

export const Route = createFileRoute("/app/settings")({ component: SettingsPage });

function SettingsPage() {
  const pathname = useRouterState({ select: (state) => state.location.pathname });
  const { selectedProject } = useProjectSelection();

  // Nested `/app/settings/api-keys` is a child route; render it via Outlet.
  if (pathname !== "/app/settings") {
    return <Outlet />;
  }

  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Project settings"
        description="Canonical project setup and machine credentials. Legacy demo settings have been removed from this surface."
      />
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 space-y-6">
          <Card title="Project API keys">
            <p className="text-[13px] text-muted-foreground leading-relaxed">
              Create scoped <span className="font-mono">hel_proj_*</span> keys for SDK and OTLP
              clients. Plaintext is shown once; Helios stores only a hash.
            </p>
            <Link
              to="/app/settings/api-keys"
              className="mt-4 inline-block border border-ink bg-ink px-3 py-2 text-[12.5px] text-paper"
            >
              Manage API keys
            </Link>
          </Card>
          <Card title="Getting started">
            <p className="text-[13px] text-muted-foreground leading-relaxed">
              Create a project, mint a key, and verify telemetry without the admin CLI.
            </p>
            <Link
              to="/app/getting-started"
              className="mt-4 inline-block border border-rule px-3 py-2 text-[12.5px] hover:bg-paper-2"
            >
              Open getting started
            </Link>
          </Card>
        </div>
        <div className="col-span-12 lg:col-span-5 space-y-6">
          <Card title="Selected project">
            {selectedProject ? (
              <div className="grid grid-cols-2 gap-3 font-mono text-[12.5px]">
                <div className="label-eyebrow">Name</div>
                <div className="truncate">{selectedProject.name}</div>
                <div className="label-eyebrow">Slug</div>
                <div className="truncate">{selectedProject.slug}</div>
                <div className="label-eyebrow">Environment</div>
                <div>{selectedProject.environment}</div>
              </div>
            ) : (
              <p className="text-[13px] text-muted-foreground">
                No project selected.{" "}
                <Link to="/app/getting-started" className="underline underline-offset-2">
                  Create one
                </Link>
                .
              </p>
            )}
          </Card>
          <Card title="Access model">
            <Eyebrow>Organization-wide</Eyebrow>
            <p className="mt-2 text-[12.5px] text-muted-foreground leading-relaxed">
              Any authenticated member of the active linked WorkOS organization can manage that
              organization&apos;s projects and API keys. Per-project roles are not implemented yet.
            </p>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="border border-rule bg-paper">
      <div className="border-b border-rule px-4 py-3">
        <h2 className="font-serif text-lg">{title}</h2>
      </div>
      <div className="px-4 py-4">{children}</div>
    </section>
  );
}
