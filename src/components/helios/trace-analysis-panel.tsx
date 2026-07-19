import { useState } from "react";

import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import type { AnalysisFinding, TraceAnalysis } from "@/lib/api/user";
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
 * Deterministic trace-analysis panel: explicit run action, evidence-backed
 * findings, telemetry coverage, and analyst limitations. Everything shown is
 * returned verbatim by the backend engine — no reinterpretation, no LLM.
 */
export function TraceAnalysisPanel({
  state,
  actionDisabled,
  knownSpanIds,
  selectedSpanId,
  onSelectSpan,
}: {
  state: TraceAnalysisState;
  /** True while the trace itself is loading/unavailable. */
  actionDisabled: boolean;
  knownSpanIds: ReadonlySet<string>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
}) {
  const { status, analysis, error, runAnalysis } = state;
  const running = status === "loading";
  const disabled = actionDisabled || running || !state.canRun;

  return (
    <section className="border border-rule bg-card" aria-label="Trace analysis">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-rule px-4 py-2.5">
        <div className="flex items-center gap-2">
          <Eyebrow>Trace analysis</Eyebrow>
          <StatusBadge tone="neutral">deterministic</StatusBadge>
        </div>
        <button
          type="button"
          onClick={runAnalysis}
          disabled={disabled}
          aria-busy={running}
          className={cn(
            "label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink",
            disabled && "opacity-50 cursor-not-allowed hover:bg-transparent",
          )}
        >
          {running ? "Analyzing…" : status === "success" ? "Run again" : "Analyze trace"}
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
}: {
  analysis: TraceAnalysis;
  knownSpanIds: ReadonlySet<string>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
}) {
  const summary = severitySummary(analysis.findings);

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
}: {
  finding: AnalysisFinding;
  knownSpanIds: ReadonlySet<string>;
  selectedSpanId: string | null;
  onSelectSpan: (spanId: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const citedSpanIds = resolveCitedSpanIds(finding.span_ids, knownSpanIds);
  const supporting = Object.entries(finding.supporting_attributes);

  const activate = () => {
    if (citedSpanIds.length > 0) onSelectSpan(citedSpanIds[0]);
  };

  return (
    <li className="px-4 py-4">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={severityTone(finding.severity)}>
          {severityLabel(finding.severity)}
        </StatusBadge>
        <span className="text-[13px] font-medium">{ruleLabel(finding.rule_id)}</span>
        <span className="font-mono text-[11px] text-muted-foreground">
          {categoryLabel(finding.category)} · {confidenceLabel(finding.confidence)}
        </span>
      </div>

      <p className="mt-2 whitespace-normal break-words text-[13px] leading-relaxed text-foreground">
        {finding.statement}
      </p>

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
