import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { MetricCard, StatusBadge, Eyebrow, ButtonLink } from "@/components/helios/primitives";
import { TRACES, statusTone } from "@/components/helios/demo-data";

export const Route = createFileRoute("/app/dashboard")({ component: DashboardPage });

function DashboardPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Workspace · acme / production"
        title="Dashboard"
        description="Sample telemetry from the last 24 hours. Demo data."
        actions={
          <>
            <ButtonLink to="/app/traces" variant="outline">View traces</ButtonLink>
            <ButtonLink to="/app/evaluations">Run evaluation</ButtonLink>
          </>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-rule">
        <MetricCard label="Total requests" value="124,891" delta={{ value: "+8.2%", tone: "up" }} hint="vs. previous 24h" />
        <MetricCard label="Avg latency" value="1.34s" delta={{ value: "−110ms", tone: "up" }} hint="p50 across models" />
        <MetricCard label="Token usage" value="48.2M" delta={{ value: "+3.1%", tone: "neutral" }} hint="prompt + completion" />
        <MetricCard label="Estimated cost" value="$ 612.40" delta={{ value: "+4.4%", tone: "down" }} hint="USD · all envs" />
        <MetricCard label="Error rate" value="1.8%" delta={{ value: "−0.4 pts", tone: "up" }} hint="5xx + tool failures" />
        <MetricCard label="Eval pass rate" value="88.1%" delta={{ value: "+3.4 pts", tone: "up" }} hint="support_qa.v4" />
        <MetricCard label="Citation coverage" value="84.1%" delta={{ value: "+1.2 pts", tone: "up" }} hint="rag.knowledge_base" />
        <MetricCard label="Active models" value="3" hint="gpt-4o · claude-3.5 · gemini-1.5" />
      </div>

      <div className="mt-10 grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8 border border-rule bg-card">
          <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
            <Eyebrow>Recent traces</Eyebrow>
            <Link to="/app/traces" className="label-eyebrow hover:text-foreground">All →</Link>
          </div>
          <div className="divide-y divide-rule">
            {TRACES.slice(0, 6).map((t) => (
              <Link
                to="/app/traces/$id"
                params={{ id: t.id }}
                key={t.id}
                className="grid grid-cols-12 items-center gap-3 px-4 py-3 hover:bg-paper-2"
              >
                <div className="col-span-3 font-mono text-[12px]">{t.id}</div>
                <div className="col-span-5 truncate text-[13px]">{t.query}</div>
                <div className="col-span-2 font-mono text-[11px] text-muted-foreground">{t.model} · {t.lat}ms</div>
                <div className="col-span-2 flex justify-end">
                  <StatusBadge tone={statusTone(t.status)}>{t.status}</StatusBadge>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-6">
          <div className="border border-rule bg-card">
            <div className="border-b border-rule px-4 py-2.5"><Eyebrow>Failing prompts</Eyebrow></div>
            <ul className="divide-y divide-rule">
              {[
                ["support.router.system / v5", "12 errs"],
                ["rag.answer.synth / v7", "8 errs"],
                ["router.classify.intent / v3", "3 errs"],
              ].map(([p, e]) => (
                <li key={p} className="flex items-center justify-between px-4 py-3">
                  <span className="font-mono text-[12px]">{p}</span>
                  <StatusBadge tone="danger">{e}</StatusBadge>
                </li>
              ))}
            </ul>
          </div>
          <div className="border border-rule bg-card">
            <div className="border-b border-rule px-4 py-2.5"><Eyebrow>Model usage</Eyebrow></div>
            <ul className="divide-y divide-rule">
              {[
                ["gpt-4o", 62],
                ["claude-3.5-sonnet", 26],
                ["gemini-1.5-pro", 9],
                ["gpt-4o-mini", 3],
              ].map(([m, pct]) => (
                <li key={m as string} className="px-4 py-3">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[12px]">{m}</span>
                    <span className="font-mono text-[11px] text-muted-foreground">{pct}%</span>
                  </div>
                  <div className="mt-2 h-1.5 bg-paper-2">
                    <div className="h-full bg-ink/85" style={{ width: `${pct}%` }} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}