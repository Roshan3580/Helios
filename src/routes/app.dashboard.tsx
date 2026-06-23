import { createFileRoute, Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { DataSourceNotice } from "@/components/helios/data-source-notice";
import { DemoOnlyAction } from "@/components/helios/demo-only-action";
import { MetricCard, StatusBadge, Eyebrow, ButtonLink } from "@/components/helios/primitives";
import { statusTone } from "@/components/helios/demo-data";
import { useDashboardSummary } from "@/hooks/use-dashboard-summary";

export const Route = createFileRoute("/app/dashboard")({ component: DashboardPage });

function DashboardPage() {
  const { data, source, loading } = useDashboardSummary();

  return (
    <div>
      <PageHeader
        eyebrow="Workspace · acme / production"
        title="Dashboard"
        description="Sample telemetry from the backend when live API mode is on. Portfolio MVP."
        actions={
          <>
            <ButtonLink to="/app/traces" variant="outline">
              View traces
            </ButtonLink>
            <DemoOnlyAction>Run evaluation</DemoOnlyAction>
          </>
        }
      />
      <DataSourceNotice source={source} />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-px bg-rule">
        {data.metrics.map((metric) => (
          <MetricCard
            key={metric.label}
            label={metric.label}
            value={loading ? "…" : metric.value}
            delta={metric.delta}
            hint={metric.hint}
          />
        ))}
      </div>

      <div className="mt-10 grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8 border border-rule bg-card">
          <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
            <Eyebrow>Recent traces</Eyebrow>
            <Link to="/app/traces" className="label-eyebrow hover:text-foreground">
              All →
            </Link>
          </div>
          <div className="divide-y divide-rule">
            {loading ? (
              <div className="px-4 py-8 text-center">
                <Eyebrow>Loading traces…</Eyebrow>
              </div>
            ) : (
              data.recentTraces.map((t) => (
                <Link
                  to="/app/traces/$id"
                  params={{ id: t.id }}
                  key={t.id}
                  className="grid grid-cols-12 items-center gap-3 px-4 py-3 hover:bg-paper-2"
                >
                  <div className="col-span-3 font-mono text-[12px]">{t.id}</div>
                  <div className="col-span-5 truncate text-[13px]">{t.query}</div>
                  <div className="col-span-2 font-mono text-[11px] text-muted-foreground">
                    {t.model} · {t.lat}ms
                  </div>
                  <div className="col-span-2 flex justify-end">
                    <StatusBadge tone={statusTone(t.status)}>{t.status}</StatusBadge>
                  </div>
                </Link>
              ))
            )}
          </div>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-6">
          <div className="border border-rule bg-card">
            <div className="border-b border-rule px-4 py-2.5">
              <Eyebrow>Failing prompts</Eyebrow>
            </div>
            <ul className="divide-y divide-rule">
              {loading ? (
                <li className="px-4 py-3">
                  <span className="label-eyebrow">Loading…</span>
                </li>
              ) : data.failingPrompts.length === 0 ? (
                <li className="px-4 py-3">
                  <span className="font-mono text-[12px] text-muted-foreground">None</span>
                </li>
              ) : (
                data.failingPrompts.map(([p, e]) => (
                  <li key={p} className="flex items-center justify-between px-4 py-3">
                    <span className="font-mono text-[12px]">{p}</span>
                    <StatusBadge tone="danger">{e}</StatusBadge>
                  </li>
                ))
              )}
            </ul>
          </div>
          <div className="border border-rule bg-card">
            <div className="border-b border-rule px-4 py-2.5">
              <Eyebrow>Model usage</Eyebrow>
            </div>
            <ul className="divide-y divide-rule">
              {loading ? (
                <li className="px-4 py-3">
                  <span className="label-eyebrow">Loading…</span>
                </li>
              ) : (
                data.modelUsage.map(([m, pct]) => (
                  <li key={m as string} className="px-4 py-3">
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-[12px]">{m}</span>
                      <span className="font-mono text-[11px] text-muted-foreground">{pct}%</span>
                    </div>
                    <div className="mt-2 h-1.5 bg-paper-2">
                      <div className="h-full bg-ink/85" style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                ))
              )}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
