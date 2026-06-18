import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";

export const Route = createFileRoute("/app/rag-analytics")({ component: RagPage });

function RagPage() {
  const metrics = [
    { l: "Retrieval hit rate", v: "92.8%", d: "+1.2% wk" },
    { l: "Citation coverage", v: "84.1%", d: "+3.4% wk" },
    { l: "Missing-source rate", v: "5.6%", d: "−0.8% wk" },
    { l: "Reranker uplift", v: "+11.4 pts", d: "vs. baseline" },
  ];
  const chunks = [
    { c: "policy-q3.md#§4.2", hit: 142, score: 0.92, tone: "success" as const },
    { c: "finance-handbook.md#§3", hit: 98, score: 0.81, tone: "success" as const },
    { c: "changelog/2025-q3.md", hit: 64, score: 0.76, tone: "warn" as const },
    { c: "security/keys.md", hit: 41, score: 0.69, tone: "warn" as const },
    { c: "legal/soc2.md", hit: 12, score: 0.51, tone: "danger" as const },
  ];
  const failing = [
    "what is the refund window for annual plans?",
    "how do I rotate API keys without downtime?",
    "is there a SOC2 type II report available?",
    "can I export traces to datadog?",
    "how does helios store our prompts?",
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Observe"
        title="RAG Analytics"
        description="Retrieval quality across your production traffic. Find missed sources and low-confidence queries."
      />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-rule mb-10">
        {metrics.map((m) => (
          <div key={m.l} className="bg-paper p-5 border border-rule">
            <div className="label-eyebrow">{m.l}</div>
            <div className="mt-3 font-serif text-3xl tracking-tight">{m.v}</div>
            <div className="mt-1 font-mono text-[11px] text-muted-foreground">{m.d}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5"><Eyebrow>Chunk quality · last 7d</Eyebrow></div>
          <div className="grid grid-cols-12 border-b border-rule px-4 py-2.5 label-eyebrow">
            <div className="col-span-6">Chunk</div>
            <div className="col-span-2">Hits</div>
            <div className="col-span-2">Score</div>
            <div className="col-span-2 text-right">Status</div>
          </div>
          {chunks.map((c) => (
            <div key={c.c} className="grid grid-cols-12 items-center border-b border-rule px-4 py-3 font-mono text-[12.5px]">
              <div className="col-span-6">{c.c}</div>
              <div className="col-span-2 text-muted-foreground">{c.hit}</div>
              <div className="col-span-2 text-muted-foreground">{c.score}</div>
              <div className="col-span-2 flex justify-end"><StatusBadge tone={c.tone}>{c.tone === "success" ? "ok" : c.tone === "warn" ? "drift" : "low"}</StatusBadge></div>
            </div>
          ))}
        </div>
        <div className="col-span-12 lg:col-span-5 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5"><Eyebrow>Top missed queries</Eyebrow></div>
          <ul className="divide-y divide-rule">
            {failing.map((q, i) => (
              <li key={q} className="flex items-center justify-between px-4 py-3">
                <span className="font-mono text-[12.5px]">{q}</span>
                <StatusBadge tone={i === 0 ? "danger" : "warn"}>0 src</StatusBadge>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}