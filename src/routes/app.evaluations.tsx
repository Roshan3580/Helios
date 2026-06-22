import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { Eyebrow, StatusBadge, ButtonLink } from "@/components/helios/primitives";

export const Route = createFileRoute("/app/evaluations")({ component: EvalsPage });

const SUITES = [
  {
    name: "support_qa.regression",
    dataset: "support_qa.v4",
    runs: 38,
    pass: 88.1,
    lat: "1.51s",
    cost: "$0.020",
  },
  {
    name: "research.summary.quality",
    dataset: "research_summaries.v2",
    runs: 14,
    pass: 91.4,
    lat: "1.78s",
    cost: "$0.015",
  },
  {
    name: "rag.citation.coverage",
    dataset: "policy_retrieval.v1",
    runs: 22,
    pass: 84.7,
    lat: "1.32s",
    cost: "$0.012",
  },
];

const COMPARE = [
  {
    p: "prompt.v1",
    m: "gpt-4o",
    acc: 82.4,
    cost: 0.018,
    lat: 1.42,
    cite: 71,
    tone: "neutral" as const,
  },
  {
    p: "prompt.v2",
    m: "gpt-4o",
    acc: 88.1,
    cost: 0.02,
    lat: 1.51,
    cite: 84,
    tone: "success" as const,
  },
  {
    p: "prompt.v2",
    m: "claude-3.5",
    acc: 86.7,
    cost: 0.015,
    lat: 1.78,
    cite: 80,
    tone: "neutral" as const,
  },
  {
    p: "prompt.v3",
    m: "gemini-1.5",
    acc: 79.3,
    cost: 0.009,
    lat: 0.94,
    cite: 62,
    tone: "warn" as const,
  },
];

function EvalsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Improve"
        title="Evaluations"
        description="Reproducible eval suites with deterministic, LLM-as-judge, and code-based scorers."
        actions={<ButtonLink to="/app/evaluations">Run evaluation</ButtonLink>}
      />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-px bg-rule">
        {SUITES.map((s) => (
          <div key={s.name} className="bg-paper p-5 border border-rule">
            <Eyebrow>{s.dataset}</Eyebrow>
            <div className="mt-3 font-serif text-2xl tracking-tight">{s.name}</div>
            <div className="mt-4 grid grid-cols-3 gap-3 font-mono text-[12px]">
              <div>
                <div className="label-eyebrow">Pass</div>
                <div>{s.pass}%</div>
              </div>
              <div>
                <div className="label-eyebrow">Lat p50</div>
                <div>{s.lat}</div>
              </div>
              <div>
                <div className="label-eyebrow">Cost</div>
                <div>{s.cost}</div>
              </div>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <span className="label-eyebrow">{s.runs} runs</span>
              <StatusBadge tone={s.pass > 88 ? "success" : "warn"}>
                {s.pass > 88 ? "passing" : "watch"}
              </StatusBadge>
            </div>
          </div>
        ))}
      </div>

      <div className="mt-10 border border-rule bg-card">
        <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
          <Eyebrow>Model comparison · support_qa.v4</Eyebrow>
          <span className="font-mono text-[11px] text-muted-foreground">run_8821 · 18s ago</span>
        </div>
        <div className="grid grid-cols-12 border-b border-rule px-4 py-2.5 label-eyebrow">
          <div className="col-span-3">Prompt</div>
          <div className="col-span-2">Model</div>
          <div className="col-span-2">Accuracy</div>
          <div className="col-span-2">Cost / run</div>
          <div className="col-span-2">Latency</div>
          <div className="col-span-1">Cite</div>
        </div>
        {COMPARE.map((r, i) => (
          <div
            key={i}
            className="grid grid-cols-12 items-center border-b border-rule px-4 py-3 font-mono text-[12.5px]"
          >
            <div className="col-span-3">{r.p}</div>
            <div className="col-span-2 text-muted-foreground">{r.m}</div>
            <div className="col-span-2">
              <StatusBadge tone={r.tone}>{r.acc}%</StatusBadge>
            </div>
            <div className="col-span-2 text-muted-foreground">${r.cost.toFixed(3)}</div>
            <div className="col-span-2 text-muted-foreground">{r.lat}s</div>
            <div className="col-span-1 text-muted-foreground">{r.cite}%</div>
          </div>
        ))}
      </div>
    </div>
  );
}
