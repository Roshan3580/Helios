import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { DataSourceNotice } from "@/components/helios/data-source-notice";
import { Eyebrow, StatusBadge, ButtonLink } from "@/components/helios/primitives";
import { useEvaluations } from "@/hooks/use-evaluations";

export const Route = createFileRoute("/app/evaluations")({ component: EvalsPage });

function EvalsPage() {
  const { data, source, loading } = useEvaluations();

  return (
    <div>
      <PageHeader
        eyebrow="Improve"
        title="Evaluations"
        description="Reproducible eval suites with deterministic, LLM-as-judge, and code-based scorers."
        actions={<ButtonLink to="/app/evaluations">Run evaluation</ButtonLink>}
      />
      <DataSourceNotice source={source} />
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-px bg-rule">
        {loading ? (
          <div className="bg-paper p-5 border border-rule col-span-full">
            <Eyebrow>Loading evaluation suites…</Eyebrow>
          </div>
        ) : (
          data.suites.map((s) => (
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
          ))
        )}
      </div>

      <div className="mt-10 border border-rule bg-card">
        <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
          <Eyebrow>{data.compareLabel}</Eyebrow>
          <span className="font-mono text-[11px] text-muted-foreground">{data.compareRunAt}</span>
        </div>
        <div className="grid grid-cols-12 border-b border-rule px-4 py-2.5 label-eyebrow">
          <div className="col-span-3">Prompt</div>
          <div className="col-span-2">Model</div>
          <div className="col-span-2">Accuracy</div>
          <div className="col-span-2">Cost / run</div>
          <div className="col-span-2">Latency</div>
          <div className="col-span-1">Cite</div>
        </div>
        {loading ? (
          <div className="px-4 py-8 text-center">
            <Eyebrow>Loading comparison…</Eyebrow>
          </div>
        ) : (
          data.compare.map((r, i) => (
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
          ))
        )}
      </div>
    </div>
  );
}
