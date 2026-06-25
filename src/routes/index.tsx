import { createFileRoute } from "@tanstack/react-router";
import { LandingHeader } from "@/components/helios/landing-header";
import { Hero } from "@/components/helios/hero";
import {
  PlatformSection,
  HowItWorksSection,
  TracesSection,
  EvaluationsSection,
  RagSection,
  CtaSection,
  LandingFooter,
} from "@/components/helios/landing-sections";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Helios: Observability for production AI systems" },
      {
        name: "description",
        content:
          "Trace, evaluate, and optimize LLM applications. Helios captures agent traces, prompt versions, RAG retrieval, evaluations, latency, and cost in one observability console.",
      },
      { property: "og:title", content: "Helios: Observability for production AI systems" },
      {
        property: "og:description",
        content:
          "Observe every trace. Improve every answer. The observability layer for production AI.",
      },
    ],
  }),
  component: Index,
});

function Index() {
  return (
    <div className="min-h-screen bg-paper text-foreground">
      <LandingHeader />
      <Hero />
      <PlatformSection />
      <HowItWorksSection />
      <TracesSection />
      <EvaluationsSection />
      <RagSection />
      <CtaSection />
      <LandingFooter />
    </div>
  );
}
