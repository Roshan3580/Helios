import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { DataSourceNotice } from "@/components/helios/data-source-notice";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";
import { useRagMetrics } from "@/hooks/use-rag-metrics";

export const Route = createFileRoute("/app/rag-analytics")({ component: RagPage });

function RagPage() {
  const { data, source, loading } = useRagMetrics();

  return (
    <div>
      <PageHeader
        eyebrow="Observe"
        title="RAG Analytics"
        description="Retrieval quality across your production traffic. Find missed sources and low-confidence queries."
      />
      <DataSourceNotice source={source} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-rule mb-10">
        {data.metrics.map((m) => (
          <div key={m.l} className="bg-paper p-5 border border-rule">
            <div className="label-eyebrow">{m.l}</div>
            <div className="mt-3 font-serif text-3xl tracking-tight">{loading ? "…" : m.v}</div>
            <div className="mt-1 font-mono text-[11px] text-muted-foreground">{m.d}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5">
            <Eyebrow>Chunk quality · last 7d</Eyebrow>
          </div>
          <div className="grid grid-cols-12 border-b border-rule px-4 py-2.5 label-eyebrow">
            <div className="col-span-6">Chunk</div>
            <div className="col-span-2">Hits</div>
            <div className="col-span-2">Score</div>
            <div className="col-span-2 text-right">Status</div>
          </div>
          {loading ? (
            <div className="px-4 py-8 text-center">
              <Eyebrow>Loading chunk metrics…</Eyebrow>
            </div>
          ) : (
            data.chunks.map((c) => (
              <div
                key={c.c}
                className="grid grid-cols-12 items-center border-b border-rule px-4 py-3 font-mono text-[12.5px]"
              >
                <div className="col-span-6">{c.c}</div>
                <div className="col-span-2 text-muted-foreground">{c.hit}</div>
                <div className="col-span-2 text-muted-foreground">{c.score}</div>
                <div className="col-span-2 flex justify-end">
                  <StatusBadge tone={c.tone}>
                    {c.tone === "success" ? "ok" : c.tone === "warn" ? "drift" : "low"}
                  </StatusBadge>
                </div>
              </div>
            ))
          )}
        </div>
        <div className="col-span-12 lg:col-span-5 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5">
            <Eyebrow>Top missed queries</Eyebrow>
          </div>
          <ul className="divide-y divide-rule">
            {loading ? (
              <li className="px-4 py-3">
                <Eyebrow>Loading…</Eyebrow>
              </li>
            ) : (
              data.failing.map((q, i) => (
                <li key={q} className="flex items-center justify-between px-4 py-3">
                  <span className="font-mono text-[12.5px]">{q}</span>
                  <StatusBadge tone={i === 0 ? "danger" : "warn"}>0 src</StatusBadge>
                </li>
              ))
            )}
          </ul>
        </div>
      </div>
    </div>
  );
}
