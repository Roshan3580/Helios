import { StatusBadge } from "./primitives";

const SPANS = [
  { name: "user.query", kind: "INPUT", ms: 0, dur: 6, depth: 0, meta: "“What changed in the Q3 revenue policy?”" },
  { name: "retriever.search", kind: "RAG", ms: 12, dur: 184, depth: 1, meta: "pgvector · top_k=8 · 12 chunks" },
  { name: "reranker.cohere", kind: "RAG", ms: 198, dur: 142, depth: 1, meta: "rerank-3 · 8 → 4" },
  { name: "llm.openai", kind: "LLM", ms: 342, dur: 812, depth: 1, meta: "gpt-4o · t=0.2 · 2,341 tok" },
  { name: "tool.lookup_policy", kind: "TOOL", ms: 1160, dur: 198, depth: 2, meta: "policy.search(scope=q3)" },
  { name: "llm.finalize", kind: "LLM", ms: 1370, dur: 52, depth: 1, meta: "gpt-4o · 318 tok" },
];

const TOTAL = 1422;

export function HeroTracePreview() {
  return (
    <div className="border border-rule bg-card shadow-[0_1px_0_rgba(0,0,0,0.02),0_24px_60px_-30px_rgba(40,30,10,0.18)]">
      <div className="flex items-center justify-between border-b border-rule px-3 py-2">
        <div className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border border-rule" />
          <span className="size-2.5 rounded-full border border-rule" />
          <span className="size-2.5 rounded-full border border-rule" />
        </div>
        <div className="font-mono text-[11px] text-muted-foreground">
          app.helios.dev / traces / trc_8f2a31e
        </div>
        <div className="label-eyebrow">LIVE</div>
      </div>
      <div className="grid grid-cols-12 gap-4 border-b border-rule px-5 py-4">
        <div className="col-span-7">
          <div className="label-eyebrow">Trace</div>
          <div className="mt-1 font-mono text-sm text-foreground">trc_8f2a31e · agent.research_assistant</div>
        </div>
        <div className="col-span-5 grid grid-cols-4 gap-3 text-right">
          <Stat label="LATENCY" value="1.42 s" />
          <Stat label="TOKENS" value="2,341" />
          <Stat label="COST" value="$0.018" />
          <Stat label="STATUS" value={<StatusBadge tone="success">ok</StatusBadge>} />
        </div>
      </div>
      <div className="divide-y divide-rule">
        {SPANS.map((s) => {
          const left = (s.ms / TOTAL) * 100;
          const width = Math.max((s.dur / TOTAL) * 100, 1.2);
          return (
            <div key={s.name} className="grid grid-cols-12 items-center gap-3 px-5 py-3">
              <div className="col-span-5 flex items-center gap-3" style={{ paddingLeft: s.depth * 16 }}>
                <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground w-12">
                  {s.kind}
                </span>
                <div>
                  <div className="font-mono text-[13px] text-foreground">{s.name}</div>
                  <div className="font-mono text-[11px] text-muted-foreground">{s.meta}</div>
                </div>
              </div>
              <div className="col-span-6 relative h-5">
                <div className="absolute inset-y-0 left-0 right-0 border-b border-dashed border-rule top-1/2" />
                <div
                  className="absolute top-1 h-3 border border-ink/70 bg-ink/85"
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
      <div className="flex items-center justify-between border-t border-rule px-5 py-3">
        <div className="flex items-center gap-2">
          <StatusBadge tone="success">success</StatusBadge>
          <StatusBadge tone="info">4 citations</StatusBadge>
          <StatusBadge tone="warn">reranker.slow</StatusBadge>
        </div>
        <div className="font-mono text-[11px] text-muted-foreground">opentelemetry · spans = 6</div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="label-eyebrow">{label}</div>
      <div className="mt-1 font-mono text-[13px] text-foreground">{value}</div>
    </div>
  );
}