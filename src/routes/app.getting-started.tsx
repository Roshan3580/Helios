import { useCallback, useEffect, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useAccessToken } from "@workos/authkit-tanstack-react-start/client";

import { PageHeader } from "@/components/helios/app-shell";
import { ProjectApiKeysPanel } from "@/components/helios/project-api-keys-panel";
import { ProjectCreateForm } from "@/components/helios/project-create-form";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import { useProjectSelection } from "@/contexts/project-selection";
import { useProjectApiKeys } from "@/hooks/use-project-api-keys";
import { fetchUserProjectTraces, UserApiError, type OtelTraceSummary } from "@/lib/api/user";
import { redirectToSignIn } from "@/lib/auth/redirect-to-sign-in";
import { API_BASE_URL } from "@/lib/api/client";

export const Route = createFileRoute("/app/getting-started")({
  component: GettingStartedPage,
});

type TelemetryState =
  | { status: "idle" }
  | { status: "checking" }
  | { status: "none" }
  | { status: "received"; trace: OtelTraceSummary }
  | { status: "error"; message: string };

function GettingStartedPage() {
  const {
    projects,
    selectedProject,
    loading: projectLoading,
    error: projectError,
    refreshProjects,
    selectProject,
  } = useProjectSelection();
  const { getAccessToken } = useAccessToken();
  const keys = useProjectApiKeys(selectedProject?.id ?? null);
  const [telemetry, setTelemetry] = useState<TelemetryState>({ status: "idle" });
  const [createdStep, setCreatedStep] = useState(false);

  useEffect(() => {
    setTelemetry({ status: "idle" });
  }, [selectedProject?.id]);

  const checkTraces = useCallback(async () => {
    if (!selectedProject) return;
    setTelemetry({ status: "checking" });
    try {
      const token = await getAccessToken();
      if (!token) {
        redirectToSignIn();
        return;
      }
      const rows = await fetchUserProjectTraces(token, selectedProject.id, {
        limit: 1,
      });
      if (rows.length === 0) {
        setTelemetry({ status: "none" });
        return;
      }
      setTelemetry({ status: "received", trace: rows[0] });
    } catch (err) {
      if (err instanceof UserApiError && err.status === 401) {
        redirectToSignIn();
        return;
      }
      setTelemetry({
        status: "error",
        message: err instanceof UserApiError ? err.message : "Unable to check telemetry",
      });
    }
  }, [selectedProject, getAccessToken]);

  const hasActiveKey = keys.keys.some((key) => key.status === "active");
  const endpointBase = API_BASE_URL || "<HELIOS_ENDPOINT>";

  if (projectLoading) {
    return (
      <div>
        <PageHeader
          eyebrow="Setup"
          title="Getting started"
          description="Create a project, mint a project API key, and send your first trace."
        />
        <p className="text-[13px] text-muted-foreground" aria-busy="true">
          Loading projects…
        </p>
      </div>
    );
  }

  if (projectError) {
    return (
      <div>
        <PageHeader
          eyebrow="Setup"
          title="Getting started"
          description="Create a project, mint a project API key, and send your first trace."
        />
        <div className="border border-rule bg-paper-2 px-4 py-4" role="alert">
          <p className="text-[13px]">{projectError}</p>
          <button
            type="button"
            onClick={refreshProjects}
            className="mt-3 border border-rule px-2.5 py-1.5 text-[12px] hover:bg-paper"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (projects.length === 0) {
    return (
      <div>
        <PageHeader
          eyebrow="Setup"
          title="Create your first project"
          description="Projects group telemetry for one application or environment inside your linked WorkOS organization. No CLI is required."
        />
        <div className="max-w-xl border border-rule bg-paper px-4 py-5">
          <ProjectCreateForm
            onCreated={(projectId) => {
              selectProject(projectId);
              setCreatedStep(true);
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        eyebrow="Setup"
        title="Getting started"
        description="Finish project setup, create a scoped API key, configure the SDK, and confirm telemetry arrives."
      />

      {createdStep ? (
        <p className="mb-4 text-[13px] text-muted-foreground" role="status">
          Project created. Continue with an API key below.
        </p>
      ) : null}

      <ol className="mb-8 space-y-3 border border-rule divide-y divide-rule">
        <ChecklistRow
          done={Boolean(selectedProject)}
          title="Project selected"
          body={
            selectedProject
              ? `${selectedProject.name} (${selectedProject.slug})`
              : "Select a project in the sidebar."
          }
        />
        <ChecklistRow
          done={hasActiveKey}
          title="API key created"
          body={
            hasActiveKey
              ? "At least one active project API key exists."
              : "Create a key with traces:ingest (and usually traces:read)."
          }
        />
        <ChecklistRow
          done={false}
          instructional
          title="SDK or OTLP configured"
          body="Install and configure the Helios SDK or a raw OTLP exporter on your machine. Helios cannot detect local installation."
        />
        <ChecklistRow
          done={telemetry.status === "received"}
          title="First trace received"
          body={
            telemetry.status === "received"
              ? `Latest trace ${telemetry.trace.trace_id}`
              : telemetry.status === "none"
                ? "No telemetry received yet."
                : telemetry.status === "error"
                  ? telemetry.message
                  : "Click Check for traces after you export."
          }
        />
        <ChecklistRow
          done={telemetry.status === "received"}
          title="Open traces"
          body="Inspect ingested traces in the Traces view."
        />
      </ol>

      {selectedProject ? (
        <div className="mb-10">
          <ProjectApiKeysPanel
            projectId={selectedProject.id}
            projectName={selectedProject.name}
            projectSlug={selectedProject.slug}
          />
        </div>
      ) : null}

      <section className="mb-10 border border-rule">
        <div className="border-b border-rule px-4 py-3">
          <h2 className="font-serif text-lg">Python SDK</h2>
        </div>
        <div className="space-y-3 px-4 py-4 text-[13px]">
          <p className="text-muted-foreground">
            Verified against the repository SDK (`helios-sdk`). Replace the placeholder with your
            one-time key (never commit it).
          </p>
          <pre className="overflow-x-auto border border-rule bg-paper-2 px-3 py-3 font-mono text-[11.5px] whitespace-pre-wrap">{`pip install -e "sdk/python[otel,openai]"

export HELIOS_API_KEY=<YOUR_HELIOS_PROJECT_KEY>
export HELIOS_ENDPOINT=${endpointBase}
export HELIOS_SERVICE_NAME=my-agent

python - <<'PY'
import os
from helios_sdk import Helios

helios = Helios.configure(
    api_key=os.environ["HELIOS_API_KEY"],
    service_name=os.environ["HELIOS_SERVICE_NAME"],
    endpoint=os.environ.get("HELIOS_ENDPOINT"),
)
helios.instrument_openai()  # content capture off by default

with helios.agent("my-agent"):
    with helios.tool("lookup") as span:
        span.set_attribute("tool.name", "demo")

helios.force_flush()
helios.shutdown()
PY`}</pre>
        </div>
      </section>

      <section className="mb-10 border border-rule">
        <div className="border-b border-rule px-4 py-3">
          <h2 className="font-serif text-lg">Raw OTLP HTTP</h2>
        </div>
        <div className="space-y-3 px-4 py-4 text-[13px]">
          <p className="text-muted-foreground">
            Canonical path: <span className="font-mono">POST /v1/otlp/traces</span> with protobuf
            body and a Bearer project API key that includes{" "}
            <span className="font-mono">traces:ingest</span>.
          </p>
          <pre className="overflow-x-auto border border-rule bg-paper-2 px-3 py-3 font-mono text-[11.5px] whitespace-pre-wrap">{`curl -X POST "${endpointBase}/v1/otlp/traces" \\
  -H "Authorization: Bearer <YOUR_HELIOS_PROJECT_KEY>" \\
  -H "Content-Type: application/x-protobuf" \\
  --data-binary @export.bin`}</pre>
        </div>
      </section>

      <section className="border border-rule">
        <div className="border-b border-rule px-4 py-3">
          <h2 className="font-serif text-lg">Telemetry check</h2>
        </div>
        <div className="space-y-3 px-4 py-4">
          <button
            type="button"
            onClick={() => void checkTraces()}
            disabled={!selectedProject || telemetry.status === "checking"}
            aria-busy={telemetry.status === "checking"}
            className="border border-rule px-3 py-2 text-[12.5px] hover:bg-paper-2 disabled:opacity-50"
          >
            {telemetry.status === "checking" ? "Checking…" : "Check for traces"}
          </button>
          <div role="status" className="text-[13px]">
            {telemetry.status === "idle" ? (
              <span className="text-muted-foreground">Not checked yet.</span>
            ) : null}
            {telemetry.status === "none" ? <span>No telemetry received yet.</span> : null}
            {telemetry.status === "error" ? <span role="alert">{telemetry.message}</span> : null}
            {telemetry.status === "received" ? (
              <div className="space-y-1">
                <div>
                  Telemetry received ·{" "}
                  <span className="font-mono text-[12px]">{telemetry.trace.trace_id}</span>
                </div>
                <div className="text-muted-foreground text-[12px]">
                  {telemetry.trace.root_span_name || "root span unknown"} ·{" "}
                  {telemetry.trace.start_time}
                </div>
                <Link
                  to="/app/traces/$id"
                  params={{ id: telemetry.trace.trace_id }}
                  className="text-[12.5px] underline underline-offset-2"
                >
                  Open trace
                </Link>
              </div>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2 pt-2">
            <Link
              to="/app/traces"
              className="border border-rule px-2.5 py-1.5 text-[12px] hover:bg-paper-2"
            >
              Open traces
            </Link>
            <Link
              to="/app/dashboard"
              className="border border-rule px-2.5 py-1.5 text-[12px] hover:bg-paper-2"
            >
              Open dashboard
            </Link>
            <Link
              to="/app/insights"
              className="border border-rule px-2.5 py-1.5 text-[12px] hover:bg-paper-2"
            >
              Open insights
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}

function ChecklistRow({
  done,
  title,
  body,
  instructional = false,
}: {
  done: boolean;
  title: string;
  body: string;
  instructional?: boolean;
}) {
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      <StatusBadge tone={done ? "success" : instructional ? "neutral" : "warn"}>
        {done ? "done" : instructional ? "manual" : "todo"}
      </StatusBadge>
      <div className="min-w-0">
        <Eyebrow>{title}</Eyebrow>
        <p className="mt-1 text-[13px] text-muted-foreground leading-snug">{body}</p>
      </div>
    </li>
  );
}
