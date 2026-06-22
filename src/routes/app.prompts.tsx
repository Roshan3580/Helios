import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { DataSourceNotice } from "@/components/helios/data-source-notice";
import { Eyebrow, StatusBadge, ButtonLink } from "@/components/helios/primitives";
import { usePrompts } from "@/hooks/use-prompts";

export const Route = createFileRoute("/app/prompts")({ component: PromptsPage });

function PromptsPage() {
  const { prompts, source, loading } = usePrompts();

  return (
    <div>
      <PageHeader
        eyebrow="Improve"
        title="Prompt versions"
        description="Version your prompts as first-class artifacts. Diff, score, and promote across model providers."
        actions={<ButtonLink to="/app/prompts">New prompt</ButtonLink>}
      />
      <DataSourceNotice source={source} />
      <div className="border border-rule bg-card">
        <div className="grid grid-cols-12 gap-3 border-b border-rule px-4 py-2.5 label-eyebrow">
          <div className="col-span-3">Prompt</div>
          <div className="col-span-1">Latest</div>
          <div className="col-span-2">Model</div>
          <div className="col-span-2">Eval score</div>
          <div className="col-span-1 text-right">Latency</div>
          <div className="col-span-1 text-right">Cost</div>
          <div className="col-span-2 text-right">Updated</div>
        </div>
        {loading ? (
          <div className="px-4 py-8 text-center">
            <Eyebrow>Loading prompts…</Eyebrow>
          </div>
        ) : (
          prompts.map((p) => (
            <div
              key={p.name}
              className="grid grid-cols-12 items-center gap-3 border-b border-rule px-4 py-3"
            >
              <div className="col-span-3">
                <div className="font-mono text-[12.5px]">{p.name}</div>
                <div className="label-eyebrow mt-0.5">{p.versions} versions</div>
              </div>
              <div className="col-span-1 font-mono text-[12px]">{p.latest}</div>
              <div className="col-span-2 font-mono text-[12px] text-muted-foreground">
                {p.model}
              </div>
              <div className="col-span-2">
                <StatusBadge tone={p.score > 85 ? "success" : p.score > 80 ? "warn" : "danger"}>
                  {p.score}%
                </StatusBadge>
              </div>
              <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                {p.lat}
              </div>
              <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                {p.cost}
              </div>
              <div className="col-span-2 text-right">
                <span className="font-mono text-[11px] text-muted-foreground">{p.updated}</span>
              </div>
            </div>
          ))
        )}
      </div>
      <div className="mt-10 grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5 flex justify-between items-center">
            <Eyebrow>Diff · support.router.system v5 → v6</Eyebrow>
            <span className="font-mono text-[11px] text-muted-foreground">+12 / −4 lines</span>
          </div>
          <pre className="font-mono text-[12px] p-4 whitespace-pre-wrap">{`  You are the support router for Helios.
- Classify intents into: billing, technical, account.
+ Classify intents into: billing, technical, account, security.
+ If the user mentions API keys or tokens, prefer "security".
  Always cite the source document.`}</pre>
        </div>
        <div className="col-span-12 lg:col-span-5 border border-rule bg-card">
          <div className="border-b border-rule px-4 py-2.5">
            <Eyebrow>Score history</Eyebrow>
          </div>
          <ul className="divide-y divide-rule">
            {[
              ["v6", "88.1%", "success"],
              ["v5", "82.4%", "warn"],
              ["v4", "79.0%", "warn"],
              ["v3", "74.2%", "danger"],
            ].map(([v, s, t]) => (
              <li key={v as string} className="flex items-center justify-between px-4 py-3">
                <span className="font-mono text-[12px]">{v}</span>
                <StatusBadge tone={t as "success" | "warn" | "danger"}>{s}</StatusBadge>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
