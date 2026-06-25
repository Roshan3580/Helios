import { Eyebrow, SectionHeader, StatusBadge } from "./primitives";
import { Activity, GitCompare, ListChecks, Search, Coins, Bug } from "lucide-react";

const FEATURES = [
  {
    icon: Activity,
    label: "01 / TRACING",
    title: "Trace every request",
    body: "Capture every LLM call, tool call, retrieval step, and generated answer as a nested span tree with timings and metadata.",
  },
  {
    icon: GitCompare,
    label: "02 / PROMPTS",
    title: "Compare prompt versions",
    body: "Version prompts as first-class artifacts. Diff outputs, scores, latency, and cost across model providers.",
  },
  {
    icon: ListChecks,
    label: "03 / EVALUATIONS",
    title: "Run eval suites",
    body: "Score model output against fixed datasets with deterministic, LLM-as-judge, and code-based evaluators.",
  },
  {
    icon: Search,
    label: "04 / RAG",
    title: "Monitor RAG quality",
    body: "Measure retrieval hit rate, citation coverage, and missing-source analysis on production traffic.",
  },
  {
    icon: Coins,
    label: "05 / COST",
    title: "Track cost and latency",
    body: "Aggregate token usage and spend by model, prompt, environment, and customer. Set per-project budgets.",
  },
  {
    icon: Bug,
    label: "06 / DEBUG",
    title: "Debug agent failures",
    body: "Replay agent runs from the first user input to the final response with deterministic seeds and tool inputs.",
  },
];

export function PlatformSection() {
  return (
    <section id="platform" className="border-t border-rule">
      <div className="mx-auto max-w-[1320px] px-6 py-24">
        <div className="flex items-end justify-between gap-12 mb-14">
          <SectionHeader
            eyebrow="The Platform"
            title={
              <>
                Everything your AI system does,
                <br className="hidden md:block" /> captured in one place.
              </>
            }
            description="Helios is built for engineers running agents, RAG, and LLM pipelines in production. One observability console for traces, evaluations, prompts, retrieval quality, cost, and latency."
          />
          <div className="hidden md:block label-eyebrow text-right">§ Platform: 06 modules</div>
        </div>
        <div className="grid grid-cols-1 border-l border-t border-rule md:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => {
            const Icon = f.icon;
            return (
              <div
                key={f.title}
                className="group border-r border-b border-rule p-7 hover:bg-paper-2 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <Icon className="size-4 text-foreground" strokeWidth={1.5} />
                  <Eyebrow>{f.label}</Eyebrow>
                </div>
                <div className="mt-10 font-serif text-2xl tracking-tight text-foreground">
                  {f.title}
                </div>
                <p className="mt-2 max-w-sm text-[14px] leading-relaxed text-muted-foreground">
                  {f.body}
                </p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

const PIPELINE = [
  {
    step: "I.",
    title: "Instrument SDK",
    body: "@helios/sdk for Python, TS, Go. One line wraps your LLM client.",
  },
  {
    step: "II.",
    title: "Capture trace",
    body: "OpenTelemetry-compatible spans for calls, tools, retrievers.",
  },
  {
    step: "III.",
    title: "Store spans",
    body: "Append-only event log with replayable inputs and outputs.",
  },
  {
    step: "IV.",
    title: "Evaluate output",
    body: "Score against datasets: code, regex, LLM-judge, custom.",
  },
  {
    step: "V.",
    title: "Analyze failures",
    body: "Cluster by tag, prompt version, model, customer, cost band.",
  },
  {
    step: "VI.",
    title: "Improve",
    body: "Promote prompts and retrieval configs, then re-run regressions.",
  },
];

export function HowItWorksSection() {
  return (
    <section className="border-t border-rule bg-paper-2/60">
      <div className="mx-auto max-w-[1320px] px-6 py-24">
        <SectionHeader
          eyebrow="How it works"
          title="An engineering pipeline, not a dashboard."
          description="Helios sits between your application and your model provider. Spans flow in, evaluations run continuously, regressions surface as diffs you can act on."
        />
        <div className="mt-14 grid grid-cols-1 gap-px bg-rule md:grid-cols-3 lg:grid-cols-6">
          {PIPELINE.map((p) => (
            <div key={p.step} className="bg-paper p-6">
              <div className="font-mono text-[11px] tracking-wider text-muted-foreground">
                {p.step}
              </div>
              <div className="mt-6 font-serif text-xl tracking-tight">{p.title}</div>
              <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">{p.body}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

export function TracesSection() {
  const items = [
    { d: 14, n: "user.query", k: "INPUT" },
    { d: 142, n: "retriever.pgvector", k: "RAG" },
    { d: 96, n: "reranker.cohere", k: "RAG" },
    { d: 612, n: "llm.openai.gpt-4o", k: "LLM" },
    { d: 184, n: "tool.knowledge_base.search", k: "TOOL" },
    { d: 60, n: "llm.openai.finalize", k: "LLM" },
  ];
  return (
    <section id="traces" className="border-t border-rule">
      <div className="mx-auto grid max-w-[1320px] grid-cols-12 gap-12 px-6 py-24">
        <div className="col-span-12 lg:col-span-5">
          <SectionHeader
            eyebrow="Traces"
            title="Every span. Every input. Every output."
            description="Helios records the full request graph: spans, inputs, outputs, retrieved chunks, model settings, tool calls, errors, and cost breakdowns, and links them back to the prompt version that produced them."
          />
          <ul className="mt-8 space-y-3 text-[14px] text-muted-foreground">
            {[
              "Nested span tree with timings",
              "OpenTelemetry-compatible exporter",
              "Full input/output payloads, redactable",
              "Trace-level tags, sessions, and users",
            ].map((t) => (
              <li key={t} className="flex gap-3">
                <span className="mt-2 size-1 rounded-full bg-foreground" />
                {t}
              </li>
            ))}
          </ul>
        </div>
        <div className="col-span-12 lg:col-span-7">
          <div className="border border-rule bg-card">
            <div className="flex items-center justify-between border-b border-rule px-4 py-2.5">
              <div className="font-mono text-[11px] text-muted-foreground">
                trc_a91f02d · agent.support_router
              </div>
              <StatusBadge tone="success">200 OK</StatusBadge>
            </div>
            <div className="divide-y divide-rule">
              {items.map((s, i) => (
                <div key={i} className="grid grid-cols-12 items-center gap-3 px-4 py-3">
                  <div className="col-span-2 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    {s.k}
                  </div>
                  <div className="col-span-6 font-mono text-[12.5px]">{s.n}</div>
                  <div className="col-span-3 h-2 bg-paper-2">
                    <div
                      className="h-full bg-ink/85"
                      style={{ width: `${Math.min(100, (s.d / 700) * 100)}%` }}
                    />
                  </div>
                  <div className="col-span-1 text-right font-mono text-[11px] text-muted-foreground">
                    {s.d}ms
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export function EvaluationsSection() {
  const rows = [
    {
      p: "prompt.v1",
      m: "gpt-4o",
      acc: "82.4%",
      cost: "$0.018",
      lat: "1.42s",
      cite: "71%",
      tone: "neutral" as const,
    },
    {
      p: "prompt.v2",
      m: "gpt-4o",
      acc: "88.1%",
      cost: "$0.020",
      lat: "1.51s",
      cite: "84%",
      tone: "success" as const,
    },
    {
      p: "prompt.v2",
      m: "claude-3.5",
      acc: "86.7%",
      cost: "$0.015",
      lat: "1.78s",
      cite: "80%",
      tone: "neutral" as const,
    },
    {
      p: "prompt.v3",
      m: "gemini-1.5",
      acc: "79.3%",
      cost: "$0.009",
      lat: "0.94s",
      cite: "62%",
      tone: "warn" as const,
    },
  ];
  return (
    <section id="evaluations" className="border-t border-rule bg-paper-2/60">
      <div className="mx-auto grid max-w-[1320px] grid-cols-12 gap-12 px-6 py-24">
        <div className="col-span-12 lg:col-span-7">
          <div className="border border-rule bg-card">
            <div className="grid grid-cols-12 border-b border-rule bg-paper px-4 py-2.5 label-eyebrow">
              <div className="col-span-3">Prompt</div>
              <div className="col-span-2">Model</div>
              <div className="col-span-2">Accuracy</div>
              <div className="col-span-2">Cost / run</div>
              <div className="col-span-2">Latency</div>
              <div className="col-span-1">Cite</div>
            </div>
            {rows.map((r, i) => (
              <div
                key={i}
                className="grid grid-cols-12 items-center border-b border-rule px-4 py-3 font-mono text-[12.5px]"
              >
                <div className="col-span-3">{r.p}</div>
                <div className="col-span-2 text-muted-foreground">{r.m}</div>
                <div className="col-span-2">
                  <StatusBadge tone={r.tone}>{r.acc}</StatusBadge>
                </div>
                <div className="col-span-2 text-muted-foreground">{r.cost}</div>
                <div className="col-span-2 text-muted-foreground">{r.lat}</div>
                <div className="col-span-1 text-muted-foreground">{r.cite}</div>
              </div>
            ))}
            <div className="flex items-center justify-between px-4 py-3">
              <div className="label-eyebrow">Dataset · support_qa.v4 · 412 examples</div>
              <div className="font-mono text-[11px] text-muted-foreground">run_8821 · 18s ago</div>
            </div>
          </div>
        </div>
        <div className="col-span-12 lg:col-span-5">
          <SectionHeader
            eyebrow="Evaluations"
            title="Compare prompts and models against the same dataset."
            description="Run reproducible eval suites with deterministic, LLM-as-judge, and code-based scorers. Promote the winning prompt with a single click and keep a full regression history."
          />
        </div>
      </div>
    </section>
  );
}

export function RagSection() {
  const metrics = [
    { l: "Retrieval hit rate", v: "92.8%", d: "+1.2% wk" },
    { l: "Citation coverage", v: "84.1%", d: "+3.4% wk" },
    { l: "Missing-source rate", v: "5.6%", d: "−0.8% wk" },
    { l: "Reranker uplift", v: "+11.4 pts", d: "vs. baseline" },
  ];
  const queries = [
    "what is the refund window for annual plans?",
    "how do I rotate API keys without downtime?",
    "is there a SOC2 type II report available?",
    "can I export traces to datadog?",
  ];
  return (
    <section id="rag" className="border-t border-rule">
      <div className="mx-auto max-w-[1320px] px-6 py-24">
        <SectionHeader
          eyebrow="RAG Analytics"
          title="Find what your retriever is missing."
          description="Measure retrieval quality through citation coverage and missing-source analysis. Surface the top failing queries and the chunks your retriever is consistently skipping."
        />
        <div className="mt-12 grid grid-cols-12 gap-6">
          <div className="col-span-12 grid grid-cols-2 gap-px bg-rule lg:col-span-7 lg:grid-cols-4">
            {metrics.map((m) => (
              <div key={m.l} className="bg-paper p-5">
                <div className="label-eyebrow">{m.l}</div>
                <div className="mt-3 font-serif text-3xl tracking-tight">{m.v}</div>
                <div className="mt-1 font-mono text-[11px] text-muted-foreground">{m.d}</div>
              </div>
            ))}
            <div className="col-span-2 bg-paper p-5 lg:col-span-4">
              <div className="label-eyebrow mb-3">Citation coverage · last 7d</div>
              <Spark />
            </div>
          </div>
          <div className="col-span-12 border border-rule bg-card lg:col-span-5">
            <div className="border-b border-rule px-4 py-2.5 label-eyebrow">
              Top failing queries
            </div>
            <ul className="divide-y divide-rule">
              {queries.map((q, i) => (
                <li key={q} className="flex items-center justify-between px-4 py-3">
                  <span className="font-mono text-[12.5px]">{q}</span>
                  <StatusBadge tone={i === 0 ? "danger" : "warn"}>0 src</StatusBadge>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}

function Spark() {
  const pts = [62, 64, 68, 66, 70, 72, 71, 75, 78, 76, 80, 82, 81, 84];
  const w = 600,
    h = 80;
  const path = pts
    .map(
      (p, i) => `${i === 0 ? "M" : "L"} ${(i / (pts.length - 1)) * w} ${h - ((p - 60) / 30) * h}`,
    )
    .join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-20" preserveAspectRatio="none">
      <path
        d={`${path} L ${w} ${h} L 0 ${h} Z`}
        fill="color-mix(in oklab, var(--accent-amber) 16%, transparent)"
      />
      <path d={path} fill="none" stroke="var(--ink)" strokeWidth="1.25" />
    </svg>
  );
}

export function CtaSection() {
  return (
    <section className="border-t border-rule">
      <div className="mx-auto max-w-[1320px] px-6 py-24 text-center">
        <Eyebrow className="mx-auto">Start observing</Eyebrow>
        <h2 className="mt-4 font-serif text-5xl md:text-6xl tracking-tight leading-[1.02]">
          One line of SDK.
          <br />
          <span className="italic text-ink-soft">A complete view of your AI system.</span>
        </h2>
        <div className="mx-auto mt-10 max-w-xl border border-rule bg-card p-5 text-left">
          <div className="label-eyebrow">install</div>
          <pre className="mt-2 font-mono text-[12.5px]">{`pip install helios-sdk

import helios
helios.init(api_key="hel_•••••••••")
helios.trace(openai.chat.completions.create)`}</pre>
        </div>
      </div>
    </section>
  );
}

export function LandingFooter() {
  return (
    <footer className="border-t border-rule">
      <div className="mx-auto grid max-w-[1320px] grid-cols-12 gap-6 px-6 py-12">
        <div className="col-span-12 md:col-span-5">
          <div className="font-serif text-2xl tracking-tight">Helios</div>
          <p className="mt-2 max-w-sm text-sm text-muted-foreground">
            The observability layer for production AI. Built for teams shipping agents, RAG, and LLM
            systems.
          </p>
        </div>
        {[
          { h: "Platform", l: ["Traces", "Prompts", "Evaluations", "RAG Analytics"] },
          { h: "Developers", l: ["Docs", "SDKs", "OpenTelemetry", "Changelog"] },
          { h: "Company", l: ["About", "Security", "Status", "Contact"] },
        ].map((c) => (
          <div key={c.h} className="col-span-6 md:col-span-2">
            <div className="label-eyebrow mb-3">{c.h}</div>
            <ul className="space-y-2 text-sm">
              {c.l.map((x) => (
                <li key={x}>
                  <a href="#" className="hover:text-foreground text-muted-foreground">
                    {x}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div className="col-span-12 mt-6 flex items-center justify-between border-t border-rule pt-4">
          <div className="font-mono text-[11px] text-muted-foreground">
            © {new Date().getFullYear()} Helios Observability Inc. · v1.0.0
          </div>
          <div className="label-eyebrow">All systems operational</div>
        </div>
      </div>
    </footer>
  );
}
