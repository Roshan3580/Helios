import { ButtonLink, Eyebrow } from "./primitives";
import { HeroTracePreview } from "./trace-preview";

export function Hero() {
  return (
    <section className="relative border-b border-rule">
      <div className="absolute inset-0 grid-bg opacity-[0.5] [mask-image:radial-gradient(ellipse_at_top,black,transparent_70%)]" />
      <div className="relative mx-auto max-w-[1320px] px-6 pt-16 pb-24">
        <div className="grid grid-cols-12 gap-10">
          <div className="col-span-12 lg:col-span-6">
            <div className="flex items-center gap-3">
              <Eyebrow>AI Systems Observability</Eyebrow>
              <span className="h-px w-12 bg-rule" />
              <Eyebrow>v1.0 · GA</Eyebrow>
            </div>
            <h1 className="mt-6 font-serif text-[64px] leading-[0.98] tracking-tight text-foreground md:text-[88px]">
              Observe every trace.
              <br />
              <span className="italic text-ink-soft">Improve every answer.</span>
            </h1>
            <p className="mt-7 max-w-xl text-[17px] leading-relaxed text-muted-foreground">
              Helios gives AI teams a complete view into LLM calls, agent workflows, RAG retrieval,
              prompt versions, evaluations, latency, and cost — so production AI systems can be
              debugged, measured, and improved.
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-3">
              <ButtonLink to="/app/dashboard">Open observatory →</ButtonLink>
              <ButtonLink to="/app/traces" variant="outline">View demo traces</ButtonLink>
            </div>
            <div className="mt-12 grid grid-cols-2 gap-px bg-rule sm:grid-cols-4 max-w-2xl">
              {[
                ["Agent traces", "12.4M / mo"],
                ["Prompt versions", "Diffable"],
                ["RAG analytics", "Citation-aware"],
                ["Eval runs", "Reproducible"],
              ].map(([k, v]) => (
                <div key={k} className="bg-paper px-3 py-3">
                  <div className="label-eyebrow">{k}</div>
                  <div className="mt-1 font-mono text-[12px] text-foreground">{v}</div>
                </div>
              ))}
            </div>
          </div>
          <div className="col-span-12 lg:col-span-6">
            <HeroTracePreview />
          </div>
        </div>
      </div>
    </section>
  );
}