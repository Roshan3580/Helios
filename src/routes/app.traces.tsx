import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { DataSourceNotice } from "@/components/helios/data-source-notice";
import { StatusBadge, Eyebrow } from "@/components/helios/primitives";
import { statusTone } from "@/components/helios/demo-data";
import { useTraceList } from "@/hooks/use-traces";

export const Route = createFileRoute("/app/traces")({ component: TracesLayout });

function TracesLayout() {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  const { traces, source, loading } = useTraceList();

  if (pathname !== "/app/traces") return <Outlet />;

  return (
    <div>
      <PageHeader
        eyebrow="Observe"
        title="Traces"
        description="Every request, every span. Click a trace to inspect inputs, outputs, retrieval, and tool calls."
      />
      <DataSourceNotice source={source} />
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {["All", "Errors", "Slow (>2s)", "Costly (>$0.02)", "RAG", "Agents"].map((f, i) => (
          <button
            key={f}
            className={`label-eyebrow border border-rule px-2.5 py-1 ${i === 0 ? "bg-ink text-paper border-ink" : "hover:bg-paper-2"}`}
          >
            {f}
          </button>
        ))}
        <div className="ml-auto label-eyebrow">
          {loading ? "Loading…" : `${traces.length} traces`}
        </div>
      </div>
      <div className="border border-rule bg-card">
        <div className="grid grid-cols-12 gap-3 border-b border-rule px-4 py-2.5 label-eyebrow">
          <div className="col-span-2">Trace</div>
          <div className="col-span-2">App</div>
          <div className="col-span-4">User query</div>
          <div className="col-span-1">Model</div>
          <div className="col-span-1 text-right">Latency</div>
          <div className="col-span-1 text-right">Cost</div>
          <div className="col-span-1 text-right">Status</div>
        </div>
        {loading ? (
          <div className="px-4 py-8 text-center">
            <Eyebrow>Loading traces…</Eyebrow>
          </div>
        ) : traces.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <Eyebrow>No traces found</Eyebrow>
          </div>
        ) : (
          traces.map((t) => (
            <Link
              to="/app/traces/$id"
              params={{ id: t.id }}
              key={t.id}
              className="grid grid-cols-12 items-center gap-3 border-b border-rule px-4 py-3 hover:bg-paper-2"
            >
              <div className="col-span-2 font-mono text-[12px]">{t.id}</div>
              <div className="col-span-2 font-mono text-[12px] text-muted-foreground">{t.app}</div>
              <div className="col-span-4 truncate text-[13px]">{t.query}</div>
              <div className="col-span-1 font-mono text-[11px] text-muted-foreground">
                {t.model}
              </div>
              <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                {t.lat}ms
              </div>
              <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                ${t.cost.toFixed(3)}
              </div>
              <div className="col-span-1 flex justify-end">
                <StatusBadge tone={statusTone(t.status)}>{t.status}</StatusBadge>
              </div>
            </Link>
          ))
        )}
        <div className="flex items-center justify-between px-4 py-3">
          <Eyebrow>{source === "api" ? "Stream · live" : "Stream · demo"}</Eyebrow>
          <div className="font-mono text-[11px] text-muted-foreground">
            {source === "api" ? "backend connected" : "local demo data"}
          </div>
        </div>
      </div>
    </div>
  );
}
