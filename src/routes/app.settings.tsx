import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";

export const Route = createFileRoute("/app/settings")({ component: SettingsPage });

function SettingsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Workspace"
        title="Settings"
        description="API keys, SDK installation, webhooks, and team."
      />
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-7 space-y-6">
          <Card title="API Keys">
            <ul className="divide-y divide-rule">
              {[
                ["production", "hel_live_••••••••f31a", "live"],
                ["staging", "hel_test_••••••••0c2d", "test"],
              ].map(([env, key, kind]) => (
                <li key={env} className="flex items-center justify-between px-1 py-3">
                  <div>
                    <div className="font-mono text-[12.5px]">{key}</div>
                    <div className="label-eyebrow mt-0.5">{env}</div>
                  </div>
                  <StatusBadge tone={kind === "live" ? "success" : "warn"}>{kind}</StatusBadge>
                </li>
              ))}
            </ul>
          </Card>
          <Card title="SDK setup">
            <pre className="font-mono text-[12px] whitespace-pre-wrap">{`# Python
pip install helios-sdk

import helios, openai
helios.init(api_key="hel_live_••••")
client = helios.trace(openai.OpenAI())

# TypeScript
npm i @helios/sdk
import { trace } from "@helios/sdk"
const openai = trace(new OpenAI())`}</pre>
          </Card>
          <Card title="Webhooks">
            <ul className="divide-y divide-rule">
              {[
                ["trace.failed", "https://hooks.acme.dev/helios"],
                ["eval.regressed", "https://hooks.acme.dev/evals"],
              ].map(([ev, url]) => (
                <li key={ev} className="flex items-center justify-between px-1 py-3 font-mono text-[12.5px]">
                  <span>{ev}</span>
                  <span className="text-muted-foreground">{url}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
        <div className="col-span-12 lg:col-span-5 space-y-6">
          <Card title="Project">
            <div className="grid grid-cols-2 gap-3 font-mono text-[12.5px]">
              <div className="label-eyebrow">Slug</div><div>acme/production</div>
              <div className="label-eyebrow">Region</div><div>us-east-1</div>
              <div className="label-eyebrow">Retention</div><div>90 days</div>
              <div className="label-eyebrow">PII redaction</div><div>on</div>
            </div>
          </Card>
          <Card title="Team">
            <ul className="divide-y divide-rule">
              {[
                ["Maya Mehta", "mm@helios.dev", "owner"],
                ["Kai Rodriguez", "kr@helios.dev", "admin"],
                ["AI Team", "ai-team@acme.dev", "member"],
              ].map(([n, e, r]) => (
                <li key={e} className="flex items-center justify-between px-1 py-3">
                  <div>
                    <div className="text-[13px]">{n}</div>
                    <div className="font-mono text-[11px] text-muted-foreground">{e}</div>
                  </div>
                  <span className="label-eyebrow">{r}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-rule bg-card">
      <div className="border-b border-rule px-4 py-2.5"><Eyebrow>{title}</Eyebrow></div>
      <div className="p-4">{children}</div>
    </div>
  );
}