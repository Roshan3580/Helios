import { useMemo, useState } from "react";
import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";

import { PageHeader } from "@/components/helios/app-shell";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import { useProjectSelection } from "@/contexts/project-selection";
import { useTraceList } from "@/hooks/use-traces";
import { formatDurationMs, formatTimestamp, shortTraceId } from "@/lib/otel/format";

export const Route = createFileRoute("/app/traces")({ component: TracesLayout });

function TracesLayout() {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  if (pathname !== "/app/traces") return <Outlet />;
  return <TracesListPage />;
}

function TracesListPage() {
  const { selectedProject, loading: projectLoading, error: projectError } = useProjectSelection();
  const [serviceName, setServiceName] = useState("");
  const [errorsOnly, setErrorsOnly] = useState(false);
  const [draftService, setDraftService] = useState("");

  const filters = useMemo(
    () => ({ serviceName, errorsOnly, limit: 50 }),
    [serviceName, errorsOnly],
  );
  const { traces, loading, error, errorStatus, reload } = useTraceList(filters);

  return (
    <div>
      <PageHeader
        eyebrow="Observe"
        title="Traces"
        description="Canonical OpenTelemetry traces for the selected project. Spans, timing, and errors as recorded by your instrumentation."
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
          body="No projects are available in this organization yet. Create a project before traces can be viewed."
          actionLabel="Getting started"
          actionHref="/app/getting-started"
        />
      ) : (
        <>
          <div className="mb-4 flex flex-wrap items-end gap-3">
            <div className="min-w-[180px]">
              <label htmlFor="trace-service-filter" className="label-eyebrow">
                Service name
              </label>
              <div className="mt-1 flex gap-2">
                <input
                  id="trace-service-filter"
                  value={draftService}
                  onChange={(event) => setDraftService(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") setServiceName(draftService.trim());
                  }}
                  placeholder="e.g. my-service"
                  className="w-full border border-rule bg-paper px-2.5 py-1.5 font-mono text-[12px] outline-none focus:border-ink"
                />
                <button
                  type="button"
                  onClick={() => setServiceName(draftService.trim())}
                  className="label-eyebrow border border-rule px-2.5 py-1.5 hover:bg-paper-2"
                >
                  Apply
                </button>
              </div>
            </div>
            <label className="flex items-center gap-2 border border-rule px-2.5 py-1.5 text-[12px]">
              <input
                type="checkbox"
                checked={errorsOnly}
                onChange={(event) => setErrorsOnly(event.target.checked)}
                className="size-3.5"
              />
              Errors only
            </label>
            <div className="ml-auto label-eyebrow self-center">
              {loading || projectLoading
                ? "Loading…"
                : `${traces.length} trace${traces.length === 1 ? "" : "s"}`}
            </div>
          </div>

          {error ? (
            <StatePanel
              title={
                errorStatus === 403
                  ? "Access denied"
                  : errorStatus === 404
                    ? "Not found"
                    : "Could not load traces"
              }
              body={error}
              actionLabel="Retry"
              onAction={reload}
            />
          ) : (
            <div className="border border-rule bg-card overflow-x-auto">
              <div className="min-w-[860px]">
                <div className="grid grid-cols-12 gap-3 border-b border-rule px-4 py-2.5 label-eyebrow">
                  <div className="col-span-2">Trace</div>
                  <div className="col-span-2">Service</div>
                  <div className="col-span-3">Root operation</div>
                  <div className="col-span-2">Start</div>
                  <div className="col-span-1 text-right">Duration</div>
                  <div className="col-span-1 text-right">Spans</div>
                  <div className="col-span-1 text-right">Errors</div>
                </div>
                {loading || projectLoading ? (
                  <div className="px-4 py-8 text-center" aria-busy="true">
                    <Eyebrow>Loading traces…</Eyebrow>
                  </div>
                ) : traces.length === 0 ? (
                  <div className="px-4 py-8 text-center">
                    <Eyebrow>No traces found</Eyebrow>
                    <p className="mt-2 text-sm text-muted-foreground">
                      {serviceName || errorsOnly
                        ? "No traces match the current filters."
                        : "Ingest OTLP traces into this project to see them here."}
                    </p>
                  </div>
                ) : (
                  traces.map((trace) => (
                    <Link
                      key={trace.trace_id}
                      to="/app/traces/$id"
                      params={{ id: trace.trace_id }}
                      className="grid grid-cols-12 items-center gap-3 border-b border-rule px-4 py-3 hover:bg-paper-2 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-ink"
                    >
                      <div className="col-span-2 font-mono text-[12px]" title={trace.trace_id}>
                        {shortTraceId(trace.trace_id)}
                      </div>
                      <div className="col-span-2 font-mono text-[12px] text-muted-foreground truncate">
                        {trace.service_name}
                      </div>
                      <div className="col-span-3 truncate text-[13px]">
                        {trace.root_span_name ?? "—"}
                      </div>
                      <div className="col-span-2 font-mono text-[11px] text-muted-foreground">
                        {formatTimestamp(trace.start_time)}
                      </div>
                      <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                        {formatDurationMs(trace.duration_ms)}
                      </div>
                      <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                        {trace.span_count}
                      </div>
                      <div className="col-span-1 flex justify-end">
                        {trace.error_count > 0 ? (
                          <StatusBadge tone="danger">{trace.error_count}</StatusBadge>
                        ) : (
                          <span className="font-mono text-[11px] text-muted-foreground">0</span>
                        )}
                      </div>
                    </Link>
                  ))
                )}
                <div className="flex items-center justify-between px-4 py-3">
                  <Eyebrow>
                    {selectedProject
                      ? `${selectedProject.slug} · ${selectedProject.environment}`
                      : "No project"}
                  </Eyebrow>
                  <div className="font-mono text-[11px] text-muted-foreground">
                    /v2/user/projects/…/traces
                  </div>
                </div>
              </div>
            </div>
          )}
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
  actionHref,
}: {
  title: string;
  body: string;
  actionLabel?: string;
  onAction?: () => void;
  actionHref?: "/app/getting-started";
}) {
  return (
    <div className="border border-rule bg-card px-6 py-10 text-center" role="alert">
      <Eyebrow>{title}</Eyebrow>
      <p className="mt-3 text-sm text-muted-foreground max-w-lg mx-auto">{body}</p>
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
