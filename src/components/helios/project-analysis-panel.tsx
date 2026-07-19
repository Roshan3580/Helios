import { StatusBadge } from "@/components/helios/primitives";
import { ProjectFindingCard } from "@/components/helios/project-finding-card";
import type { ProjectAnalysis } from "@/lib/api/user";
import { severityLabel, severityTone } from "@/lib/analyst/format";
import { anyExamplesTruncated, projectSeveritySummary } from "@/lib/analyst/project-format";
import { formatInteger, formatTimestamp } from "@/lib/otel/format";
import type { ProjectAnalysisState } from "@/hooks/use-project-analysis";

/**
 * Deterministic project-window analysis results with an optional narrative
 * section. Deterministic findings are the primary surface; the narrative only
 * explains existing evidence IDs and never invents findings or links.
 */
export function ProjectAnalysisPanel({ state }: { state: ProjectAnalysisState }) {
  const { status, analysis, error, runAnalysis, narrativeRequestStatus } = state;
  const running = status === "loading";
  const narrativeLoading = narrativeRequestStatus === "loading";

  return (
    <section className="border border-rule bg-card" aria-label="Project analysis results">
      {status === "idle" ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">
          Run a deterministic comparison of the selected time window against the immediately
          preceding equal-length window. Findings are computed from stored OpenTelemetry traces and
          spans by a fixed rule set — nothing is persisted and no analysis runs until you start it.
        </p>
      ) : null}

      {running ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground" role="status">
          Analyzing project telemetry windows…
        </p>
      ) : null}

      {status === "error" && error ? (
        <div className="px-4 py-6" role="alert">
          <p className="text-[13px] text-muted-foreground">{error}</p>
          <button
            type="button"
            onClick={runAnalysis}
            className="mt-3 label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "success" && analysis ? (
        <AnalysisBody
          analysis={analysis}
          generateExplanation={state.generateExplanation}
          narrativeLoading={narrativeLoading}
        />
      ) : null}
    </section>
  );
}

function AnalysisBody({
  analysis,
  generateExplanation,
  narrativeLoading,
}: {
  analysis: ProjectAnalysis;
  generateExplanation: () => void;
  narrativeLoading: boolean;
}) {
  const summary = projectSeveritySummary(analysis.findings);
  const explanationsById = new Map(
    (analysis.narrative?.finding_explanations ?? []).map((item) => [item.evidence_id, item]),
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-rule px-4 py-2.5 text-[11.5px] font-mono text-muted-foreground">
        <span>ruleset {analysis.analysis_version}</span>
        <span>generated {formatTimestamp(analysis.generated_at)}</span>
        <span>
          {analysis.findings.length} finding{analysis.findings.length === 1 ? "" : "s"}
        </span>
        {summary.map(({ severity, count }) => (
          <StatusBadge key={severity} tone={severityTone(severity)}>
            {count} {severityLabel(severity)}
          </StatusBadge>
        ))}
      </div>

      <CoverageSummary analysis={analysis} />

      <NarrativeSection
        analysis={analysis}
        narrativeLoading={narrativeLoading}
        generateExplanation={generateExplanation}
      />

      {analysis.findings.length === 0 ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">
          No findings were produced by the current project-window rule set. This does not certify
          that the project is healthy, optimal, or regression-free.
        </p>
      ) : (
        <ul className="divide-y divide-rule" aria-label="Project findings">
          {analysis.findings.map((finding) => (
            <ProjectFindingCard
              key={finding.evidence_id}
              finding={finding}
              explanation={explanationsById.get(finding.evidence_id)}
            />
          ))}
        </ul>
      )}

      <div className="border-t border-rule px-4 py-4">
        <h3 className="label-eyebrow">Analyst limitations</h3>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[12.5px] text-muted-foreground">
          {analysis.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function CoverageSummary({ analysis }: { analysis: ProjectAnalysis }) {
  const coverage = analysis.coverage;
  const entries: [string, string][] = [
    ["Current traces", formatInteger(coverage.current_trace_count)],
    ["Baseline traces", formatInteger(coverage.baseline_trace_count)],
    ["Current spans", formatInteger(coverage.current_span_count)],
    ["Baseline spans", formatInteger(coverage.baseline_span_count)],
    ["Current error traces", formatInteger(coverage.current_error_trace_count)],
    ["Baseline error traces", formatInteger(coverage.baseline_error_trace_count)],
    ["Services observed", formatInteger(coverage.services_observed)],
    ["Models observed", formatInteger(coverage.models_observed)],
    ["Model-like spans", formatInteger(coverage.model_like_span_count)],
    ["With token data", formatInteger(coverage.spans_with_token_data)],
  ];
  const truncated = anyExamplesTruncated(analysis.bounds);
  return (
    <div className="border-b border-rule px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="label-eyebrow">Data coverage</h3>
        <span className="font-mono text-[11px] text-muted-foreground">
          {formatTimestamp(analysis.current_window.start)} →{" "}
          {formatTimestamp(analysis.current_window.end)} vs baseline{" "}
          {formatTimestamp(analysis.baseline_window.start)} →{" "}
          {formatTimestamp(analysis.baseline_window.end)}
        </span>
      </div>
      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
        {entries.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-1.5 text-[12px]">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-mono text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
      {coverage.baseline_sample_sparse ? (
        <p className="mt-2 text-[12px] text-muted-foreground">
          The baseline window is sparse, which reduces confidence in regression comparisons.
        </p>
      ) : null}
      {truncated ? (
        <p className="mt-2 text-[12px] text-muted-foreground" role="status">
          Some example or candidate lists were truncated by configured caps; aggregate counts still
          cover all matching telemetry.
        </p>
      ) : null}
    </div>
  );
}

function NarrativeSection({
  analysis,
  narrativeLoading,
  generateExplanation,
}: {
  analysis: ProjectAnalysis;
  narrativeLoading: boolean;
  generateExplanation: () => void;
}) {
  const narrativeStatus = analysis.narrative_status ?? "not_requested";
  const showGenerateButton = narrativeStatus !== "disabled" && analysis.findings.length > 0;

  return (
    <div className="border-b border-rule px-4 py-4" aria-label="Optional explanation">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="label-eyebrow">Optional explanation</h3>
        {showGenerateButton ? (
          <button
            type="button"
            onClick={generateExplanation}
            disabled={narrativeLoading}
            aria-busy={narrativeLoading}
            className="label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {narrativeLoading
              ? "Generating explanation…"
              : narrativeStatus === "complete"
                ? "Regenerate explanation"
                : "Generate explanation"}
          </button>
        ) : null}
      </div>

      <p className="mt-2 text-[12px] text-muted-foreground">
        Deterministic findings are always primary. An optional explanation may send bounded,
        redacted finding metadata to the configured third-party provider. Trace IDs, prompts,
        completions, tool output, documents, credentials, and identity are excluded.
      </p>

      {narrativeLoading ? (
        <p className="mt-3 text-[13px] text-muted-foreground" role="status">
          Generating explanation…
        </p>
      ) : null}

      {!narrativeLoading && narrativeStatus === "disabled" ? (
        <p className="mt-3 text-[13px] text-muted-foreground" role="status">
          Narrative explanation is not enabled for this Helios environment.
        </p>
      ) : null}

      {!narrativeLoading && narrativeStatus === "failed" ? (
        <div className="mt-3" role="alert">
          <p className="text-[13px] text-muted-foreground">
            The optional explanation could not be generated. Deterministic findings remain available
            below.
          </p>
          <button
            type="button"
            onClick={generateExplanation}
            className="mt-2 label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            Retry explanation
          </button>
        </div>
      ) : null}

      {!narrativeLoading && narrativeStatus === "complete" && analysis.narrative ? (
        <div className="mt-4 space-y-4">
          <div>
            <h4 className="text-[12px] font-medium text-foreground">Summary</h4>
            <p className="mt-1 whitespace-normal break-words text-[13px] leading-relaxed">
              {analysis.narrative.summary}
            </p>
          </div>
          {analysis.narrative.caveats.length > 0 ? (
            <div>
              <h4 className="text-[12px] font-medium text-foreground">Explanation caveats</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-[12.5px] text-muted-foreground">
                {analysis.narrative.caveats.map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <p className="text-[11.5px] text-muted-foreground">
            Per-finding explanations appear inside the matching finding cards below.
          </p>
        </div>
      ) : null}

      {!narrativeLoading && narrativeStatus === "not_requested" ? (
        <p className="mt-3 text-[13px] text-muted-foreground">
          No optional explanation has been requested for this analysis.
        </p>
      ) : null}
    </div>
  );
}
