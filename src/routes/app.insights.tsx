import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";

import { PageHeader } from "@/components/helios/app-shell";
import { ProjectAnalysisPanel } from "@/components/helios/project-analysis-panel";
import { useProjectSelection } from "@/contexts/project-selection";
import { useProjectAnalysis } from "@/hooks/use-project-analysis";

export const Route = createFileRoute("/app/insights")({ component: InsightsPage });

type InsightsHours = 24 | 168 | 720;

const TIME_WINDOWS: { hours: InsightsHours; label: string }[] = [
  { hours: 24, label: "Last 24 hours" },
  { hours: 168, label: "Last 7 days" },
  { hours: 720, label: "Last 30 days" },
];

function InsightsPage() {
  const {
    selectedProject,
    loading: projectLoading,
    error: projectError,
    reload,
  } = useProjectSelection();
  const [hours, setHours] = useState<InsightsHours>(24);
  const state = useProjectAnalysis(hours);

  const eyebrow = selectedProject
    ? `${selectedProject.slug} · ${selectedProject.environment}`
    : "Observe";
  const running = state.status === "loading";
  const narrativeLoading = state.narrativeRequestStatus === "loading";
  const disabled = running || narrativeLoading || !state.canRun;

  return (
    <div>
      <PageHeader
        eyebrow={eyebrow}
        title="Project insights"
        description="Deterministic comparison of canonical telemetry windows: the selected window against the immediately preceding equal-length window. Analysis runs only when you start it and nothing is persisted."
      />

      {projectError ? (
        <StatePanel
          title="Project unavailable"
          body={projectError}
          actionLabel="Retry"
          onAction={reload}
        />
      ) : !projectLoading && !selectedProject ? (
        <StatePanel
          title="No project selected"
          body="No projects are linked to the active organization. An administrator must link or create a project before insights can run."
        />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="min-w-[200px]">
              <label htmlFor="insights-window" className="label-eyebrow">
                Time window
              </label>
              <select
                id="insights-window"
                value={hours}
                onChange={(event) => setHours(Number(event.target.value) as InsightsHours)}
                disabled={running || narrativeLoading}
                className="mt-1 w-full border border-rule bg-paper px-2.5 py-1.5 font-mono text-[12px] outline-none focus:border-ink"
              >
                {TIME_WINDOWS.map((option) => (
                  <option key={option.hours} value={option.hours}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              onClick={state.status === "success" ? state.rerunAnalysis : state.runAnalysis}
              disabled={disabled}
              aria-busy={running || narrativeLoading}
              className="label-eyebrow border border-rule px-4 py-2 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {running
                ? "Analyzing…"
                : narrativeLoading
                  ? "Generating explanation…"
                  : state.status === "success"
                    ? "Run again"
                    : "Analyze project"}
            </button>
            <div className="ml-auto label-eyebrow self-center">
              {projectLoading ? "Loading project…" : null}
            </div>
          </div>

          <ProjectAnalysisPanel state={state} />
        </>
      )}
    </div>
  );
}

function StatePanel({
  title,
  body,
  actionLabel,
  onAction,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <div className="border border-rule bg-card px-4 py-8">
      <h2 className="font-serif text-xl tracking-tight">{title}</h2>
      <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-muted-foreground">{body}</p>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="mt-4 label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
