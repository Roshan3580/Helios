import { createFileRoute, Link } from "@tanstack/react-router";

import { PageHeader } from "@/components/helios/app-shell";
import { BackendStateNotice } from "@/components/helios/backend-state-notice";
import { Eyebrow, MetricCard, StatusBadge, ButtonLink } from "@/components/helios/primitives";
import { useProjectSelection } from "@/contexts/project-selection";
import { useDashboardSummary, type DashboardHours } from "@/hooks/use-dashboard-summary";
import type { ProjectDashboard } from "@/lib/api/user";
import {
  formatDurationMs,
  formatInteger,
  formatPercent,
  formatTimestamp,
  formatTokenTotal,
  shortTraceId,
} from "@/lib/otel/format";

export const Route = createFileRoute("/app/dashboard")({ component: DashboardPage });

const TIME_WINDOWS: { hours: DashboardHours; label: string }[] = [
  { hours: 24, label: "Last 24 hours" },
  { hours: 168, label: "Last 7 days" },
  { hours: 720, label: "Last 30 days" },
];

function DashboardPage() {
  const {
    selectedProject,
    loading: projectLoading,
    error: projectError,
    errorStatus: projectErrorStatus,
  } = useProjectSelection();
  const { data, hours, setHours, loading, error, errorStatus, reload } = useDashboardSummary();

  const eyebrow = selectedProject
    ? `${selectedProject.slug} · ${selectedProject.environment}`
    : "Observe";

  return (
    <div>
      <PageHeader
        eyebrow={eyebrow}
        title="Dashboard"
        description="Canonical OpenTelemetry aggregates for the selected project. Metrics use stored traces and spans only — no estimated cost or demo fallback."
        actions={
          <ButtonLink to="/app/traces" variant="outline">
            View traces
          </ButtonLink>
        }
      />

      {projectError ? (
        <BackendStateNotice error={projectError} status={projectErrorStatus} onRetry={reload} />
      ) : !projectLoading && !selectedProject ? (
        <StatePanel
          title="No project selected"
          body="No projects are available in this organization yet. Create a project to load the dashboard."
          actionLabel="Getting started"
          actionHref="/app/getting-started"
        />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="min-w-[200px]">
              <label htmlFor="dashboard-window" className="label-eyebrow">
                Time window
              </label>
              <select
                id="dashboard-window"
                value={hours}
                onChange={(event) => setHours(Number(event.target.value) as DashboardHours)}
                className="mt-1 w-full border border-rule bg-paper px-2.5 py-1.5 font-mono text-[12px] outline-none focus:border-ink"
              >
                {TIME_WINDOWS.map((option) => (
                  <option key={option.hours} value={option.hours}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="ml-auto label-eyebrow self-center">
              {loading || projectLoading
                ? "Loading…"
                : data
                  ? `${formatTimestamp(data.window_start)} → ${formatTimestamp(data.window_end)}`
                  : null}
            </div>
          </div>

          {error ? (
            <BackendStateNotice error={error} status={errorStatus} onRetry={reload} />
          ) : loading || projectLoading || !data ? (
            <div className="border border-rule bg-card px-4 py-10 text-center">
              <Eyebrow>Loading telemetry…</Eyebrow>
            </div>
          ) : data.overview.trace_count === 0 ? (
            <StatePanel
              title="No traces in this window"
              body="No OpenTelemetry traces were recorded for this project in the selected time window."
              actionLabel="Retry"
              onAction={reload}
            />
          ) : (
            <DashboardBody data={data} />
          )}
        </>
      )}
    </div>
  );
}

function DashboardBody({ data }: { data: ProjectDashboard }) {
  const { overview, tokens, services, models, recent_errors } = data;

  return (
    <>
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-px bg-rule">
        <MetricCard
          label="Traces"
          value={formatInteger(overview.trace_count)}
          hint="In selected window"
        />
        <MetricCard
          label="Error rate"
          value={formatPercent(overview.trace_error_rate)}
          hint={`${formatInteger(overview.error_trace_count)} error traces`}
        />
        <MetricCard
          label="p50 latency"
          value={formatDurationMs(overview.p50_duration_ms)}
          hint="Trace duration"
        />
        <MetricCard
          label="p95 latency"
          value={formatDurationMs(overview.p95_duration_ms)}
          hint="Trace duration"
        />
        <MetricCard
          label="Spans"
          value={formatInteger(overview.total_span_count)}
          hint="Across all traces"
        />
        <MetricCard
          label="Total tokens"
          value={formatTokenTotal(tokens.total_tokens, tokens.spans_with_token_data)}
          hint={
            tokens.spans_with_token_data > 0
              ? `${formatInteger(tokens.input_tokens)} in · ${formatInteger(tokens.output_tokens)} out`
              : "From gen_ai.usage.* when present"
          }
        />
      </div>

      <div className="mt-10 grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 border border-rule bg-card">
          <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
            <Eyebrow>Service health</Eyebrow>
            <span className="label-eyebrow">
              {services.length} service{services.length === 1 ? "" : "s"}
            </span>
          </div>
          {services.length === 0 ? (
            <div className="px-4 py-6">
              <span className="font-mono text-[12px] text-muted-foreground">No services</span>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left">
                <thead>
                  <tr className="border-b border-rule text-[10px] uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-2 font-medium">Service</th>
                    <th className="px-3 py-2 font-medium">Traces</th>
                    <th className="px-3 py-2 font-medium">Errors</th>
                    <th className="px-3 py-2 font-medium">p50</th>
                    <th className="px-3 py-2 font-medium">p95</th>
                    <th className="px-3 py-2 font-medium">Spans</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-rule">
                  {services.map((row) => (
                    <tr key={row.service_name}>
                      <td
                        className="max-w-[180px] truncate px-4 py-2.5 font-mono text-[12px]"
                        title={row.service_name}
                      >
                        {row.service_name}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px]">
                        {formatInteger(row.trace_count)}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px]">
                        {formatInteger(row.error_trace_count)}{" "}
                        <span className="text-muted-foreground">
                          ({formatPercent(row.error_rate)})
                        </span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px]">
                        {formatDurationMs(row.p50_duration_ms)}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px]">
                        {formatDurationMs(row.p95_duration_ms)}
                      </td>
                      <td className="px-3 py-2.5 font-mono text-[12px]">
                        {formatInteger(row.total_spans)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="col-span-12 lg:col-span-5 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5">
            <Eyebrow>Model usage</Eyebrow>
          </div>
          {models.length === 0 ? (
            <div className="px-4 py-6">
              <p className="font-mono text-[12px] text-muted-foreground">
                No model telemetry in this window. Model rows appear when spans include{" "}
                <span className="text-foreground">gen_ai.request.model</span> or{" "}
                <span className="text-foreground">gen_ai.response.model</span>.
              </p>
            </div>
          ) : (
            <ul className="divide-y divide-rule">
              {models.map((row) => (
                <li key={row.model} className="px-4 py-3">
                  <div className="flex items-start justify-between gap-3">
                    <span className="min-w-0 truncate font-mono text-[12px]" title={row.model}>
                      {row.model}
                    </span>
                    <span className="shrink-0 font-mono text-[11px] text-muted-foreground">
                      {formatInteger(row.span_count)} spans
                    </span>
                  </div>
                  <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[11px] text-muted-foreground">
                    <span>{formatInteger(row.input_tokens + row.output_tokens)} tokens</span>
                    <span>{formatInteger(row.error_span_count)} errors</span>
                    <span>avg {formatDurationMs(row.avg_duration_ms)}</span>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-6 border border-rule bg-card">
        <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
          <Eyebrow>Recent errors</Eyebrow>
          <Link to="/app/traces" className="label-eyebrow hover:text-foreground">
            All traces →
          </Link>
        </div>
        {recent_errors.length === 0 ? (
          <div className="px-4 py-6">
            <span className="font-mono text-[12px] text-muted-foreground">
              No error traces in this window
            </span>
          </div>
        ) : (
          <div className="divide-y divide-rule">
            {recent_errors.map((row) => (
              <Link
                key={row.trace_id}
                to="/app/traces/$id"
                params={{ id: row.trace_id }}
                className="grid grid-cols-12 items-center gap-3 px-4 py-3 hover:bg-paper-2"
              >
                <div className="col-span-3 font-mono text-[12px]" title={row.trace_id}>
                  {shortTraceId(row.trace_id)}
                </div>
                <div className="col-span-3 truncate font-mono text-[12px]" title={row.service_name}>
                  {row.service_name}
                </div>
                <div
                  className="col-span-3 truncate text-[13px]"
                  title={row.root_span_name ?? undefined}
                >
                  {row.root_span_name ?? "—"}
                </div>
                <div className="col-span-2 font-mono text-[11px] text-muted-foreground">
                  {formatDurationMs(row.duration_ms)}
                </div>
                <div className="col-span-1 flex justify-end">
                  <StatusBadge tone="danger">{row.error_count}</StatusBadge>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </>
  );
}

function StatePanel({
  title,
  body,
  actionLabel,
  onAction,
  actionHref,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
  actionHref?: "/app/getting-started";
}) {
  return (
    <div className="border border-rule bg-card px-4 py-8">
      <h2 className="font-serif text-xl tracking-tight">{title}</h2>
      <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-muted-foreground">{body}</p>
      {actionLabel && actionHref ? (
        <Link
          to={actionHref}
          className="mt-4 inline-block label-eyebrow border border-rule px-3 py-1.5 hover:bg-paper-2"
        >
          {actionLabel}
        </Link>
      ) : actionLabel && onAction ? (
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
