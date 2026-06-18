import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { Eyebrow, StatusBadge, ButtonLink } from "@/components/helios/primitives";

export const Route = createFileRoute("/app/experiments")({ component: ExperimentsPage });

const EXPS = [
  { name: "exp_router_security_intent", status: "running" as const, base: "v5", cand: "v6", lift: "+5.7 pts" },
  { name: "exp_rag_reranker_cohere_v3", status: "winning" as const, base: "rerank-2", cand: "rerank-3", lift: "+11.4 pts" },
  { name: "exp_summarizer_claude", status: "regressed" as const, base: "gpt-4o", cand: "claude-3.5", lift: "−1.2 pts" },
];

function ExperimentsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Improve"
        title="Experiments"
        description="A/B prompts, models, and retrieval configs against live traffic."
        actions={<ButtonLink to="/app/experiments">New experiment</ButtonLink>}
      />
      <div className="border border-rule bg-card">
        <div className="grid grid-cols-12 border-b border-rule px-4 py-2.5 label-eyebrow">
          <div className="col-span-5">Experiment</div>
          <div className="col-span-2">Baseline</div>
          <div className="col-span-2">Candidate</div>
          <div className="col-span-2">Lift</div>
          <div className="col-span-1 text-right">Status</div>
        </div>
        {EXPS.map((e) => (
          <div key={e.name} className="grid grid-cols-12 items-center border-b border-rule px-4 py-3 font-mono text-[12.5px]">
            <div className="col-span-5">{e.name}</div>
            <div className="col-span-2 text-muted-foreground">{e.base}</div>
            <div className="col-span-2 text-muted-foreground">{e.cand}</div>
            <div className="col-span-2">{e.lift}</div>
            <div className="col-span-1 flex justify-end">
              <StatusBadge tone={e.status === "winning" ? "success" : e.status === "regressed" ? "danger" : "info"}>{e.status}</StatusBadge>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-8"><Eyebrow>Sample data · for preview only</Eyebrow></div>
    </div>
  );
}