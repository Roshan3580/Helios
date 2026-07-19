import { useEffect, useMemo, useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";

import { PageHeader } from "@/components/helios/app-shell";
import { SpanInspector } from "@/components/helios/span-inspector";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import { useProjectSelection } from "@/contexts/project-selection";
import { useTraceDetail } from "@/hooks/use-trace-detail";
import type { OtelSpan } from "@/lib/api/user";
import {
  formatDurationMs,
  formatTimestamp,
  isOtelErrorStatus,
  otelSpanKindLabel,
  otelStatusLabel,
  otelStatusTone,
} from "@/lib/otel/format";
import { buildTimelineRows, timelineTotalMs } from "@/lib/otel/timeline";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/app/traces/$id")({ component: TraceDetailPage });

function TraceDetailPage() {
  const { id } = Route.useParams();
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectSelection();
  const { trace, loading, error, errorStatus, reload } = useTraceDetail(id);

  const rows = useMemo(() => (trace ? buildTimelineRows(trace.spans) : []), [trace]);
  const total = timelineTotalMs(rows);
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null);

  useEffect(() => {
    if (!trace) {
      setSelectedSpanId(null);
      return;
    }
    const preferred =
      (trace.root_span_id && trace.spans.find((span) => span.span_id === trace.root_span_id)) ||
      rows[0]?.span ||
      null;
    setSelectedSpanId(preferred?.span_id ?? null);
  }, [trace, rows]);

  const selectedSpan: OtelSpan | null =
    trace?.spans.find((span) => span.span_id === selectedSpanId) ?? null;

  if (projectLoading || loading) {
    return (
      <div>
        <BackLink />
        <div className="mt-8 px-4 py-8 text-center" aria-busy="true">
          <Eyebrow>Loading trace…</Eyebrow>
        </div>
      </div>
    );
  }

  if (projectError) {
    return (
      <div>
        <BackLink />
        <StatePanel
          title="Project unavailable"
          body={projectError}
          actionLabel="Retry"
          onAction={reload}
        />
      </div>
    );
  }

  if (!selectedProject) {
    return (
      <div>
        <BackLink />
        <StatePanel
          title="No project selected"
          body="Select a project in the sidebar before opening a trace."
        />
      </div>
    );
  }

  if (error) {
    return (
      <div>
        <BackLink />
        <StatePanel
          title={
            errorStatus === 403
              ? "Access denied"
              : errorStatus === 404
                ? "Trace not found"
                : "Could not load trace"
          }
          body={error}
          actionLabel="Retry"
          onAction={reload}
        />
      </div>
    );
  }

  if (!trace) {
    return (
      <div>
        <BackLink />
        <StatePanel
          title="Trace not found"
          body="This trace was not found in the selected project."
        />
      </div>
    );
  }

  return (
    <div>
      <BackLink />
      <PageHeader
        eyebrow={`Trace · ${trace.service_name}`}
        title={trace.trace_id}
        description={trace.root_span_name ?? "Root operation not recorded"}
        actions={
          <StatusBadge tone={trace.error_count > 0 ? "danger" : "success"}>
            {trace.error_count > 0 ? `${trace.error_count} errors` : "ok"}
          </StatusBadge>
        }
      />

      <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-rule mb-8">
        <Cell label="Service" value={trace.service_name} />
        <Cell label="Environment" value={trace.environment ?? "—"} />
        <Cell label="Duration" value={formatDurationMs(trace.duration_ms)} />
        <Cell label="Spans" value={String(trace.span_count)} />
      </div>
      <div className="mb-8 grid grid-cols-1 md:grid-cols-3 gap-3 text-[12.5px]">
        <Meta label="Start" value={formatTimestamp(trace.start_time)} />
        <Meta label="End" value={formatTimestamp(trace.end_time)} />
        <Meta label="Project" value={`${trace.project_slug} · ${selectedProject.environment}`} />
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 border border-rule bg-card min-w-0">
          <div className="border-b border-rule px-4 py-2.5">
            <Eyebrow>Timeline · {rows.length} spans</Eyebrow>
          </div>
          {rows.length === 0 ? (
            <div className="px-4 py-8 text-center">
              <Eyebrow>No spans recorded</Eyebrow>
            </div>
          ) : (
            <div className="divide-y divide-rule" role="listbox" aria-label="Trace timeline">
              {rows.map((row) => {
                const left = (row.offsetMs / total) * 100;
                const width = Math.max(
                  (row.durationMs / total) * 100,
                  row.durationMs === 0 ? 0.4 : 1,
                );
                const selected = row.span.span_id === selectedSpanId;
                const errored = isOtelErrorStatus(row.span.status_code);
                return (
                  <button
                    key={row.span.span_id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    onClick={() => setSelectedSpanId(row.span.span_id)}
                    className={cn(
                      "grid w-full grid-cols-12 items-center gap-3 px-4 py-3 text-left hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ink",
                      selected && "bg-paper-2",
                    )}
                  >
                    <div
                      className="col-span-4 flex items-center gap-2 min-w-0"
                      style={{ paddingLeft: row.depth * 14 }}
                    >
                      <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground w-14 shrink-0">
                        {otelSpanKindLabel(row.span.kind)}
                      </span>
                      <span className="font-mono text-[12.5px] truncate">{row.span.name}</span>
                    </div>
                    <div className="col-span-6 relative h-4">
                      <div className="absolute inset-x-0 top-1/2 border-b border-dashed border-rule" />
                      <div
                        className={cn(
                          "absolute top-0.5 h-3 border",
                          errored
                            ? "bg-[color-mix(in_oklab,var(--accent-danger)_70%,var(--ink))] border-[color:var(--accent-danger)]"
                            : "bg-ink/85 border-ink/70",
                        )}
                        style={{ left: `${left}%`, width: `${width}%` }}
                      />
                    </div>
                    <div className="col-span-2 flex items-center justify-end gap-2">
                      {errored ? (
                        <StatusBadge tone={otelStatusTone(row.span.status_code)}>
                          {otelStatusLabel(row.span.status_code)}
                        </StatusBadge>
                      ) : null}
                      <span className="font-mono text-[11px] text-muted-foreground">
                        {formatDurationMs(row.durationMs)}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <div className="col-span-12 lg:col-span-5 min-w-0">
          <SpanInspector span={selectedSpan} />
        </div>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link to="/app/traces" className="label-eyebrow hover:text-foreground">
      ← All traces
    </Link>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-paper p-4 min-w-0">
      <div className="label-eyebrow">{label}</div>
      <div className="mt-2 font-serif text-2xl tracking-tight truncate" title={value}>
        {value}
      </div>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-rule bg-card px-3 py-2 min-w-0">
      <div className="label-eyebrow">{label}</div>
      <div className="mt-1 font-mono text-[12px] truncate" title={value}>
        {value}
      </div>
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
    <div className="mt-8 border border-rule bg-card px-6 py-10 text-center" role="alert">
      <Eyebrow>{title}</Eyebrow>
      <p className="mt-3 text-sm text-muted-foreground max-w-lg mx-auto">{body}</p>
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
