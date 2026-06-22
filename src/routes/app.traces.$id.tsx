import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { StatusBadge, Eyebrow } from "@/components/helios/primitives";
import { TRACES } from "@/components/helios/demo-data";

export const Route = createFileRoute("/app/traces/$id")({ component: TraceDetail });

const SPANS = [
  { name: "user.query", kind: "INPUT", ms: 0, dur: 6, depth: 0 },
  { name: "retriever.pgvector", kind: "RAG", ms: 12, dur: 184, depth: 1 },
  { name: "reranker.cohere", kind: "RAG", ms: 198, dur: 142, depth: 1 },
  { name: "llm.openai.gpt-4o", kind: "LLM", ms: 342, dur: 812, depth: 1 },
  { name: "tool.lookup_policy", kind: "TOOL", ms: 1160, dur: 198, depth: 2 },
  { name: "llm.openai.finalize", kind: "LLM", ms: 1370, dur: 52, depth: 1 },
];
const TOTAL = 1422;

function TraceDetail() {
  const { id } = Route.useParams();
  const t = TRACES.find((x) => x.id === id) ?? TRACES[0];
  return (
    <div>
      <Link to="/app/traces" className="label-eyebrow hover:text-foreground">
        ← All traces
      </Link>
      <PageHeader
        eyebrow={`Trace · ${t.app}`}
        title={t.id}
        description={t.query}
        actions={
          <StatusBadge
            tone={t.status === "success" ? "success" : t.status === "warn" ? "warn" : "danger"}
          >
            {t.status}
          </StatusBadge>
        }
      />

      <div className="grid grid-cols-4 gap-px bg-rule mb-8">
        <Cell l="Latency" v={`${t.lat} ms`} />
        <Cell l="Tokens" v={t.tok.toLocaleString()} />
        <Cell l="Cost" v={`$${t.cost.toFixed(3)}`} />
        <Cell l="Model" v={t.model} />
      </div>

      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5">
            <Eyebrow>Timeline · {SPANS.length} spans</Eyebrow>
          </div>
          <div className="divide-y divide-rule">
            {SPANS.map((s) => {
              const left = (s.ms / TOTAL) * 100;
              const width = Math.max((s.dur / TOTAL) * 100, 1);
              return (
                <div key={s.name} className="grid grid-cols-12 items-center gap-3 px-4 py-3">
                  <div
                    className="col-span-4 flex items-center gap-3"
                    style={{ paddingLeft: s.depth * 14 }}
                  >
                    <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground w-10">
                      {s.kind}
                    </span>
                    <span className="font-mono text-[12.5px]">{s.name}</span>
                  </div>
                  <div className="col-span-7 relative h-4">
                    <div className="absolute inset-x-0 top-1/2 border-b border-dashed border-rule" />
                    <div
                      className="absolute top-0.5 h-3 bg-ink/85 border border-ink/70"
                      style={{ left: `${left}%`, width: `${width}%` }}
                    />
                  </div>
                  <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                    {s.dur}ms
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="col-span-12 lg:col-span-5 space-y-6">
          <SpanCard title="Inputs">
            <pre className="font-mono text-[12px] whitespace-pre-wrap">{`{
  "query": "${t.query}",
  "user": "u_8821",
  "session": "sess_1140a"
}`}</pre>
          </SpanCard>
          <SpanCard title="Retrieved chunks">
            <ul className="divide-y divide-rule">
              {[
                "policy-q3.md#§4.2",
                "policy-q3.md#§5.1",
                "finance-handbook.md#§3",
                "changelog/2025-q3.md",
              ].map((c, i) => (
                <li key={c} className="flex items-center justify-between px-1 py-2">
                  <span className="font-mono text-[12px]">{c}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">
                    score {0.92 - i * 0.04}
                  </span>
                </li>
              ))}
            </ul>
          </SpanCard>
          <SpanCard title="Final answer">
            <p className="text-[13px] leading-relaxed">
              The Q3 revenue policy updates the recognition threshold for annual contracts from
              net-45 to net-30, and clarifies treatment of usage-based add-ons. See §4.2 for the
              recognition table and §5.1 for the transition rules.
            </p>
          </SpanCard>
          <SpanCard title="Cost breakdown">
            <div className="grid grid-cols-2 gap-2 font-mono text-[12px]">
              <div>prompt</div>
              <div className="text-right">1,820 tok · $0.011</div>
              <div>completion</div>
              <div className="text-right">521 tok · $0.006</div>
              <div>reranker</div>
              <div className="text-right">$0.001</div>
              <div className="border-t border-rule pt-2">total</div>
              <div className="text-right border-t border-rule pt-2">${t.cost.toFixed(3)}</div>
            </div>
          </SpanCard>
        </div>
      </div>
    </div>
  );
}

function Cell({ l, v }: { l: string; v: string }) {
  return (
    <div className="bg-paper p-4">
      <div className="label-eyebrow">{l}</div>
      <div className="mt-2 font-serif text-2xl tracking-tight">{v}</div>
    </div>
  );
}
function SpanCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-rule bg-card">
      <div className="border-b border-rule px-4 py-2.5">
        <Eyebrow>{title}</Eyebrow>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}
