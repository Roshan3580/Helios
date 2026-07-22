import { useState } from "react";

import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import type {
  AnalysisFinding,
  TraceAnalysis,
  TraceAnalysisFindingExplanation,
} from "@/lib/api/user";
import {
  categoryLabel,
  confidenceLabel,
  formatObservedValue,
  ruleLabel,
  severityLabel,
  severitySummary,
  severityTone,
} from "@/lib/analyst/format";
import { formatTimestamp } from "@/lib/otel/format";
import type { TraceAnalysisState } from "@/hooks/use-trace-analysis";
import { resolveCitedSpanIds } from "@/lib/analyst/span-selectors";
import { cn } from "@/lib/utils";

/**
 * Deterministic trace-analysis panel with an optional narrative section.
 * Deterministic findings remain the primary surface; narrative only explains
 * existing evidence IDs and never invents findings.
 */
export function TraceAnalysisPanel({
  state,
  actionDisabled,
  knownSpanIds,
  selectedSpanId,
  onSelectSpan,
}: {
  state: TraceAnalysisState;
  actionDisabled: boolean;
  knownSpanIds: ReadonlySet<string>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
}) {
  const {
    status,
    analysis,
    error,
    runAnalysis,
    generateExplanation,
    rerunAnalysis,
    narrativeRequestStatus,
  } = state;
  const running = status === "loading";
  const narrativeLoading = narrativeRequestStatus === "loading";
  const disabled = actionDisabled || running || narrativeLoading || !state.canRun;

  return (
    <section className="border border-rule bg-card" aria-label="Trace analysis">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Eyebrow>Trace analysis</Eyebrow>
          <StatusBadge tone="neutral">deterministic</StatusBadge>
        </div>
        <button
          type="button"
          onClick={status === "success" ? rerunAnalysis : runAnalysis}
          disabled={disabled}
          aria-busy={running || narrativeLoading}
          className={cn(
            "label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink",
            disabled && "opacity-50 cursor-not-allowed hover:bg-transparent",
          )}
        >
          {running
            ? "Analyzing…"
            : narrativeLoading
              ? "Generating explanation…"
              : status === "success"
                ? "Run again"
                : "Analyze trace"}
        </button>
      </div>

      {status === "idle" ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">
          Run a deterministic evidence analysis of this trace. Findings are computed from stored
          telemetry by a fixed rule set — no generative model is involved and nothing is persisted.
        </p>
      ) : null}

      {running ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground" role="status">
          Analyzing trace telemetry…
        </p>
      ) : null}

      {status === "error" && error ? (
        <div className="px-4 py-6" role="alert">
          <p className="text-[13px] text-muted-foreground">{error}</p>
          <button
            type="button"
            onClick={runAnalysis}
            className="mt-3 label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2"
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "success" && analysis ? (
        <AnalysisBody
          analysis={analysis}
          knownSpanIds={knownSpanIds}
          selectedSpanId={selectedSpanId}
          onSelectSpan={onSelectSpan}
          generateExplanation={generateExplanation}
          narrativeLoading={narrativeLoading}
          actionDisabled={disabled}
        />
      ) : null}
    </section>
  );
}

function AnalysisBody({
  analysis,
  knownSpanIds,
  selectedSpanId,
  onSelectSpan,
  generateExplanation,
  narrativeLoading,
  actionDisabled,
}: {
  analysis: TraceAnalysis;
  knownSpanIds: ReadonlySet<string>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
  generateExplanation: () => void;
  narrativeLoading: boolean;
  actionDisabled: boolean;
}) {
  const summary = severitySummary(analysis.findings);
  const narrativeStatus = analysis.narrative_status ?? "not_requested";
  const explanationsById = new Map(
    (analysis.narrative?.finding_explanations ?? []).map((item) => [item.evidence_id, item]),
  );

  const selectFindingSpans = (finding: AnalysisFinding) => {
    const cited = resolveCitedSpanIds(finding.span_ids, knownSpanIds);
    if (cited[0]) onSelectSpan(cited[0]);
  };

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

      <CoverageStrip analysis={analysis} />

      <NarrativeSection
        analysis={analysis}
        narrativeStatus={narrativeStatus}
        narrativeLoading={narrativeLoading}
        actionDisabled={actionDisabled}
        generateExplanation={generateExplanation}
        onSelectEvidence={(evidenceId) => {
          const finding = analysis.findings.find((item) => item.evidence_id === evidenceId);
          if (finding) selectFindingSpans(finding);
        }}
      />

      {analysis.findings.length === 0 ? (
        <p className="px-4 py-6 text-[13px] text-muted-foreground">
          No findings were produced by the current deterministic rule set. This does not certify
          that the trace is healthy or optimal.
        </p>
      ) : (
        <ul className="divide-y divide-rule" aria-label="Findings">
          {analysis.findings.map((finding) => (
            <FindingCard
              key={finding.evidence_id}
              finding={finding}
              knownSpanIds={knownSpanIds}
              selectedSpanId={selectedSpanId}
              onSelectSpan={onSelectSpan}
              explanation={explanationsById.get(finding.evidence_id)}
            />
          ))}
        </ul>
      )}

      <div className="border-t border-rule px-4 py-4">
        <Eyebrow>Analyst limitations</Eyebrow>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-[12.5px] text-muted-foreground">
          {analysis.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function NarrativeSection({
  analysis,
  narrativeStatus,
  narrativeLoading,
  actionDisabled,
  generateExplanation,
  onSelectEvidence,
}: {
  analysis: TraceAnalysis;
  narrativeStatus: string;
  narrativeLoading: boolean;
  actionDisabled: boolean;
  generateExplanation: () => void;
  onSelectEvidence: (evidenceId: string) => void;
}) {
  const showGenerateButton =
    narrativeStatus !== "disabled" &&
    (narrativeStatus === "not_requested" ||
      narrativeStatus === "failed" ||
      narrativeStatus === "complete");

  return (
    <div className="border-b border-rule px-4 py-4" aria-label="Optional explanation">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Eyebrow>Optional explanation</Eyebrow>
        {showGenerateButton ? (
          <button
            type="button"
            onClick={generateExplanation}
            disabled={actionDisabled || narrativeLoading}
            aria-busy={narrativeLoading}
            className={cn(
              "label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink",
              (actionDisabled || narrativeLoading) &&
                "opacity-50 cursor-not-allowed hover:bg-transparent",
            )}
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
        redacted evidence metadata to the configured third-party provider. Prompt, completion,
        tool-output, retrieval-document, credential, and identity content are excluded.
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
            disabled={actionDisabled}
            className="mt-2 label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2"
          >
            Retry explanation
          </button>
        </div>
      ) : null}

      {!narrativeLoading && narrativeStatus === "complete" && analysis.narrative ? (
        <div className="mt-4 space-y-4">
          <div>
            <h3 className="text-[12px] font-medium text-foreground">Summary</h3>
            <p className="mt-1 whitespace-normal break-words text-[13px] leading-relaxed">
              {analysis.narrative.summary}
            </p>
          </div>
          {analysis.narrative.finding_explanations.length > 0 ? (
            <ul className="space-y-3" aria-label="Finding explanations">
              {analysis.narrative.finding_explanations.map((item) => (
                <li key={item.evidence_id} className="border border-rule bg-paper px-3 py-2.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[11px] text-muted-foreground">
                      {item.evidence_id}
                    </span>
                    <button
                      type="button"
                      onClick={() => onSelectEvidence(item.evidence_id)}
                      className="label-eyebrow border border-rule px-2 py-0.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
                    >
                      View related span
                    </button>
                  </div>
                  <p className="mt-2 whitespace-normal break-words text-[13px] leading-relaxed">
                    {item.explanation}
                  </p>
                  {item.remediation ? (
                    <p className="mt-2 whitespace-normal break-words text-[12.5px] text-muted-foreground">
                      <span className="font-medium text-foreground">Suggestion: </span>
                      {item.remediation}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
          {analysis.narrative.caveats.length > 0 ? (
            <div>
              <h3 className="text-[12px] font-medium text-foreground">Explanation caveats</h3>
              <ul className="mt-1 list-disc space-y-1 pl-5 text-[12.5px] text-muted-foreground">
                {analysis.narrative.caveats.map((caveat) => (
                  <li key={caveat}>{caveat}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}

      {!narrativeLoading && narrativeStatus === "not_requested" ? (
        <p className="mt-3 text-[13px] text-muted-foreground">
          No optional explanation has been requested for this analysis.
        </p>
      ) : null}

      {!["not_requested", "disabled", "complete", "failed"].includes(narrativeStatus) &&
      !narrativeLoading ? (
        <p className="mt-3 text-[13px] text-muted-foreground" role="status">
          The optional explanation status is unavailable. Deterministic findings remain below.
        </p>
      ) : null}
    </div>
  );
}

function CoverageStrip({ analysis }: { analysis: TraceAnalysis }) {
  const coverage = analysis.coverage;
  const entries: [string, number][] = [
    ["Spans analyzed", coverage.total_spans],
    ["Error spans", coverage.error_spans],
    ["Tool-like", coverage.tool_like_spans],
    ["Model-like", coverage.model_like_spans],
    ["With model data", coverage.spans_with_model_data],
    ["With token data", coverage.spans_with_token_data],
    ["Orphans", coverage.orphan_spans],
  ];
  return (
    <div className="border-b border-rule px-4 py-3">
      <Eyebrow>Telemetry coverage</Eyebrow>
      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1.5">
        {entries.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-1.5 text-[12px]">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-mono text-foreground">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function FindingCard({
  finding,
  knownSpanIds,
  selectedSpanId,
  onSelectSpan,
  explanation,
}: {
  finding: AnalysisFinding;
  knownSpanIds: ReadonlySet<string>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
  explanation?: TraceAnalysisFindingExplanation;
}) {
  const [expanded, setExpanded] = useState(false);
  const citedSpanIds = resolveCitedSpanIds(finding.span_ids, knownSpanIds);
  const supporting = Object.entries(finding.supporting_attributes);

  const activate = () => {
    if (citedSpanIds.length > 0) onSelectSpan(citedSpanIds[0]);
  };

  return (
    <li className="px-4 py-4" id={`finding-${finding.evidence_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={severityTone(finding.severity)}>
          {severityLabel(finding.severity)}
        </StatusBadge>
        <span className="text-[13px] font-medium">{ruleLabel(finding.rule_id)}</span>
        <span className="font-mono text-[11px] text-muted-foreground">
          {categoryLabel(finding.category)} · {confidenceLabel(finding.confidence)}
        </span>
        <span className="font-mono text-[10.5px] text-muted-foreground">{finding.evidence_id}</span>
      </div>

      <p className="mt-2 whitespace-normal break-words text-[13px] leading-relaxed text-foreground">
        {finding.statement}
      </p>

      {explanation ? (
        <div className="mt-2 border border-rule bg-paper px-3 py-2">
          <Eyebrow>Explanation</Eyebrow>
          <p className="mt-1 whitespace-normal break-words text-[12.5px] leading-relaxed">
            {explanation.explanation}
          </p>
          {explanation.remediation ? (
            <p className="mt-1 whitespace-normal break-words text-[12px] text-muted-foreground">
              <span className="font-medium text-foreground">Suggestion: </span>
              {explanation.remediation}
            </p>
          ) : null}
        </div>
      ) : null}

      <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[12px]">
        <div className="flex items-baseline gap-1.5 min-w-0">
          <dt className="text-muted-foreground">Metric</dt>
          <dd className="font-mono break-all">{finding.metric_name}</dd>
        </div>
        <div className="flex items-baseline gap-1.5 min-w-0">
          <dt className="text-muted-foreground">Observed</dt>
          <dd className="font-mono break-all">{formatObservedValue(finding.observed_value)}</dd>
        </div>
        {finding.baseline_value != null ? (
          <div className="flex items-baseline gap-1.5 min-w-0">
            <dt className="text-muted-foreground">Baseline</dt>
            <dd className="font-mono break-all">{formatObservedValue(finding.baseline_value)}</dd>
          </div>
        ) : null}
      </dl>

      {citedSpanIds.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={activate}
            className="label-eyebrow border border-rule px-2.5 py-1 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            View span{citedSpanIds.length === 1 ? "" : "s"} · {citedSpanIds.length}
          </button>
          {citedSpanIds.map((spanId) => (
            <button
              key={spanId}
              type="button"
              onClick={() => onSelectSpan(spanId)}
              aria-pressed={selectedSpanId === spanId}
              className={cn(
                "border border-rule px-2 py-0.5 font-mono text-[10.5px] hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink",
                selectedSpanId === spanId && "bg-paper-2 border-ink/60",
              )}
            >
              {spanId}
            </button>
          ))}
        </div>
      ) : (
        <p className="mt-3 text-[11.5px] text-muted-foreground">
          This finding does not cite specific spans in the loaded trace.
        </p>
      )}

      {supporting.length > 0 ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            className="label-eyebrow hover:text-foreground"
          >
            {expanded
              ? "Hide supporting attributes"
              : `Supporting attributes · ${supporting.length}`}
          </button>
          {expanded ? (
            <dl className="mt-2 space-y-1">
              {supporting.map(([key, value]) => (
                <div
                  key={key}
                  className="grid grid-cols-[minmax(120px,auto)_1fr] gap-2 text-[11.5px]"
                >
                  <dt className="font-mono text-muted-foreground break-all">{key}</dt>
                  <dd className="font-mono break-all">{formatObservedValue(value)}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </li>
  );
}
