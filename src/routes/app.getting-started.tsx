import { useCallback, useEffect, useRef, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";

import { PageHeader } from "@/components/helios/app-shell";
import { BackendStateNotice } from "@/components/helios/backend-state-notice";
import { ProjectApiKeysPanel } from "@/components/helios/project-api-keys-panel";
import { ProjectCreateForm } from "@/components/helios/project-create-form";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import { useProjectSelection } from "@/contexts/project-selection";
import { useProjectApiKeys } from "@/hooks/use-project-api-keys";
import { useAuthorizedRequest } from "@/lib/api/authorized-request";
import { fetchUserProjectTraces, UserApiError } from "@/lib/api/user";
import { API_BASE_URL } from "@/lib/api/client";
import {
  beginTelemetryCheck,
  completeTelemetryCheck,
  failTelemetryCheck,
  hasOpenedTraces,
  initialTelemetryProgress,
  mayCheckTelemetry,
  pauseTelemetryCheck,
} from "@/lib/onboarding/trace-progress";

export const Route = createFileRoute("/app/getting-started")({
  component: GettingStartedPage,
});

function GettingStartedPage() {
  const {
    projects,
    selectedProject,
    loading: projectLoading,
    error: projectError,
    errorStatus: projectErrorStatus,
    refreshProjects,
    selectProject,
  } = useProjectSelection();
  const { run, ready } = useAuthorizedRequest();
  const keys = useProjectApiKeys(selectedProject?.id ?? null);
  const selectedProjectId = selectedProject?.id ?? null;
  const [telemetry, setTelemetry] = useState(() => initialTelemetryProgress(null));
  const [tracesOpened, setTracesOpened] = useState(false);
  const [createdStep, setCreatedStep] = useState(false);
  const telemetryRequest = useRef(0);

  useEffect(() => {
    telemetryRequest.current += 1;
    setTelemetry(initialTelemetryProgress(selectedProjectId));
    setTracesOpened(hasOpenedTraces(selectedProjectId));
  }, [selectedProjectId]);

  const checkTraces = useCallback(async () => {
    if (!mayCheckTelemetry(ready, selectedProjectId)) return;
    const projectId = selectedProjectId!;
    const requestId = ++telemetryRequest.current;
    setTelemetry((current) => beginTelemetryCheck(current, projectId));
    try {
      const rows = await run((token) => fetchUserProjectTraces(token, projectId, { limit: 1 }));
      if (requestId !== telemetryRequest.current) return;
      setTelemetry((current) => completeTelemetryCheck(current, projectId, rows));
    } catch (err) {
      if (requestId !== telemetryRequest.current) return;
      if (err instanceof UserApiError && err.status === 401) {
        // Bounded expiry already reported to central recovery; no redirect.
        setTelemetry((current) => pauseTelemetryCheck(current, projectId));
        return;
      }
      const message =
        err instanceof UserApiError
          ? err.status === 403
            ? "You do not have access to this project's telemetry."
            : err.message
          : "Unable to check telemetry. The backend may be waking up; retry shortly.";
      setTelemetry((current) => failTelemetryCheck(current, projectId, message));
    }
  }, [ready, selectedProjectId, run]);

  useEffect(() => {
    if (!mayCheckTelemetry(ready, selectedProjectId)) return;
    void checkTraces();
    return () => {
      telemetryRequest.current += 1;
    };
  }, [ready, selectedProjectId, checkTraces]);

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
        <BackendStateNotice
          error={projectError}
          status={projectErrorStatus}
          onRetry={refreshProjects}
        />
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
          done={telemetry.projectId === selectedProjectId && telemetry.trace !== null}
          title="First trace received"
          body={
            telemetry.projectId === selectedProjectId && telemetry.trace
              ? `Latest trace ${telemetry.trace.trace_id}`
              : telemetry.phase === "none"
                ? "No telemetry received yet."
                : telemetry.phase === "error"
                  ? (telemetry.error ?? "Unable to check telemetry.")
                  : telemetry.phase === "checking"
                    ? "Checking for stored telemetry."
                    : "Waiting until authentication is ready."
          }
        />
        <ChecklistRow
          done={tracesOpened}
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
            Verified against the repository Python SDK. Replace the placeholder with your one-time
            key (never commit it).
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

flush_completed = helios.force_flush()
helios.shutdown()
if not flush_completed:
    raise SystemExit("Export did not complete locally. Review exporter errors before retrying.")
print("Export completed locally. Check Helios to confirm trace arrival. Exporter errors are authoritative.")
PY`}</pre>
        </div>
      </section>

      <section className="mb-10 border border-rule">
        <div className="border-b border-rule px-4 py-3">
          <h2 className="font-serif text-lg">Node.js / TypeScript SDK</h2>
        </div>
        <div className="space-y-3 px-4 py-4 text-[13px]">
          <p className="text-muted-foreground">
            Verified against the repository SDK (<span className="font-mono">@helios-ai/sdk</span>
            ). Package name reserved for publication; not yet published — install it from the
            repository artifact. Replace the placeholder with your one-time key (never commit it).
          </p>
          <pre className="overflow-x-auto border border-rule bg-paper-2 px-3 py-3 font-mono text-[11.5px] whitespace-pre-wrap">{`# build the packaged artifact once (from a Helios checkout)
cd sdk/typescript && npm install && npm run build && npm pack

# in your Node app (Node ^18.19.0 || >=20.6.0)
npm install /path/to/helios-ai-sdk-0.1.0.tgz

export HELIOS_API_KEY=<YOUR_HELIOS_PROJECT_KEY>
export HELIOS_ENDPOINT=${endpointBase}
export HELIOS_SERVICE_NAME=my-agent

node --input-type=module - <<'JS'
import { Helios, toolAttributes } from "@helios-ai/sdk";

await Helios.configure({
  apiKey: process.env.HELIOS_API_KEY,
  endpoint: process.env.HELIOS_ENDPOINT,
  serviceName: process.env.HELIOS_SERVICE_NAME,
  diagnostics: "warn",
});

await Helios.trace("my-agent", async () => {
  await Helios.span(
    "tool.lookup",
    { spanType: "tool", attributes: toolAttributes({ toolName: "demo" }) },
    async () => {},
  );
});

await Helios.forceFlush();
await Helios.shutdown();
console.log(
  "Export completed locally. Check Helios to confirm trace arrival; exporter errors are authoritative.",
);
JS`}</pre>
          <p className="text-muted-foreground">
            Optional OpenAI auto-instrumentation:{" "}
            <span className="font-mono">instrumentations: {"{ openai: true }"}</span> (content
            capture stays off by default). See{" "}
            <span className="font-mono">docs/TYPESCRIPT_SDK.md</span> and{" "}
            <span className="font-mono">examples/typescript-basic</span>.
          </p>
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
            disabled={
              !mayCheckTelemetry(ready, selectedProjectId) || telemetry.phase === "checking"
            }
            aria-busy={telemetry.phase === "checking"}
            className="border border-rule px-3 py-2 text-[12.5px] hover:bg-paper-2 disabled:opacity-50"
          >
            {telemetry.phase === "checking" ? "Checking…" : "Check for traces"}
          </button>
          <div role="status" className="text-[13px]">
            {telemetry.phase === "idle" ? (
              <span className="text-muted-foreground">Waiting for an authorized check.</span>
            ) : null}
            {telemetry.phase === "checking" ? (
              <span className="text-muted-foreground">Checking stored telemetry.</span>
            ) : null}
            {telemetry.phase === "none" ? <span>No telemetry received yet.</span> : null}
            {telemetry.phase === "error" ? (
              <span role="alert">{telemetry.error ?? "Unable to check telemetry."}</span>
            ) : null}
            {telemetry.trace ? (
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
