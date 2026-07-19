import { useState } from "react";
import { Link } from "@tanstack/react-router";

import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import type { ProjectFinding, TraceAnalysisFindingExplanation } from "@/lib/api/user";
import {
  categoryLabel,
  confidenceLabel,
  formatObservedValue,
  severityLabel,
  severityTone,
} from "@/lib/analyst/format";
import { entityTypeLabel, projectRuleLabel, sampleSizeLabel } from "@/lib/analyst/project-format";
import { formatDurationMs, formatTimestamp, shortTraceId } from "@/lib/otel/format";

/**
 * One deterministic project-window finding. Text severity (never color
 * alone), factual statements verbatim from the backend, and supporting-trace
 * links built exclusively from backend-provided trace references.
 */
export function ProjectFindingCard({
  finding,
  explanation,
}: {
  finding: ProjectFinding;
  explanation?: TraceAnalysisFindingExplanation;
}) {
  const [expanded, setExpanded] = useState(false);
  const supporting = Object.entries(finding.supporting_values);

  return (
    <li className="px-4 py-4" id={`finding-${finding.evidence_id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={severityTone(finding.severity)}>
          {severityLabel(finding.severity)}
        </StatusBadge>
        <span className="text-[13px] font-medium">{projectRuleLabel(finding.rule_id)}</span>
        <span className="font-mono text-[11px] text-muted-foreground">
          {categoryLabel(finding.category)} · {confidenceLabel(finding.confidence)}
        </span>
        <span className="font-mono text-[10.5px] text-muted-foreground break-all">
          {finding.evidence_id}
        </span>
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
          <dt className="text-muted-foreground">{entityTypeLabel(finding.entity_type)}</dt>
          <dd className="font-mono break-all">{finding.entity_label}</dd>
        </div>
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
        {Object.keys(finding.sample_size).length > 0 ? (
          <div className="flex items-baseline gap-1.5 min-w-0">
            <dt className="text-muted-foreground">Sample</dt>
            <dd className="font-mono break-all">{sampleSizeLabel(finding.sample_size)}</dd>
          </div>
        ) : null}
      </dl>

      <SupportingTraces finding={finding} />

      {supporting.length > 0 ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded((value) => !value)}
            aria-expanded={expanded}
            className="label-eyebrow hover:text-foreground focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
          >
            {expanded ? "Hide supporting values" : `Supporting values · ${supporting.length}`}
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

function SupportingTraces({ finding }: { finding: ProjectFinding }) {
  if (finding.supporting_traces.length === 0) {
    return (
      <p className="mt-3 text-[11.5px] text-muted-foreground">
        This finding cites aggregate evidence without example traces.
      </p>
    );
  }
  return (
    <div className="mt-3">
      <Eyebrow>Supporting traces · {finding.supporting_traces.length}</Eyebrow>
      <ul className="mt-2 divide-y divide-rule border border-rule bg-paper">
        {finding.supporting_traces.map((trace) => (
          <li key={trace.trace_id}>
            <Link
              to="/app/traces/$id"
              params={{ id: trace.trace_id }}
              aria-label={`Open trace ${trace.trace_id} in ${trace.service_name}`}
              className="flex flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ink"
            >
              <span className="font-mono text-[11.5px]" title={trace.trace_id}>
                {shortTraceId(trace.trace_id)}
              </span>
              <span
                className="max-w-[160px] truncate font-mono text-[11.5px] text-muted-foreground"
                title={trace.service_name}
              >
                {trace.service_name}
              </span>
              <span
                className="max-w-[200px] truncate text-[12px]"
                title={trace.root_span_name ?? undefined}
              >
                {trace.root_span_name ?? "—"}
              </span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {formatTimestamp(trace.start_time)}
              </span>
              <span className="font-mono text-[11px] text-muted-foreground">
                {formatDurationMs(trace.duration_ms)}
              </span>
              {trace.error_count > 0 ? (
                <StatusBadge tone="danger">{trace.error_count} errors</StatusBadge>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
