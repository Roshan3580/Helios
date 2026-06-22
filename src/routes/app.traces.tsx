import { createFileRoute, Link, Outlet, useRouterState } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { StatusBadge, Eyebrow } from "@/components/helios/primitives";
import { TRACES, statusTone } from "@/components/helios/demo-data";

export const Route = createFileRoute("/app/traces")({ component: TracesLayout });

function TracesLayout() {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  // If a child route is active, render only the outlet.
  if (pathname !== "/app/traces") return <Outlet />;

  return (
    <div>
      <PageHeader
        eyebrow="Observe"
        title="Traces"
        description="Every request, every span. Click a trace to inspect inputs, outputs, retrieval, and tool calls."
      />
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {["All", "Errors", "Slow (>2s)", "Costly (>$0.02)", "RAG", "Agents"].map((f, i) => (
          <button
            key={f}
            className={`label-eyebrow border border-rule px-2.5 py-1 ${i === 0 ? "bg-ink text-paper border-ink" : "hover:bg-paper-2"}`}
          >
            {f}
          </button>
        ))}
        <div className="ml-auto label-eyebrow">{TRACES.length} of 12,481</div>
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
        {TRACES.map((t) => (
          <Link
            to="/app/traces/$id"
            params={{ id: t.id }}
            key={t.id}
            className="grid grid-cols-12 items-center gap-3 border-b border-rule px-4 py-3 hover:bg-paper-2"
          >
            <div className="col-span-2 font-mono text-[12px]">{t.id}</div>
            <div className="col-span-2 font-mono text-[12px] text-muted-foreground">{t.app}</div>
            <div className="col-span-4 truncate text-[13px]">{t.query}</div>
            <div className="col-span-1 font-mono text-[11px] text-muted-foreground">{t.model}</div>
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
        ))}
        <div className="flex items-center justify-between px-4 py-3">
          <Eyebrow>Stream · live</Eyebrow>
          <div className="font-mono text-[11px] text-muted-foreground">
            ingest rate · 1.2k spans/s
          </div>
        </div>
      </div>
    </div>
  );
}
