import { Link } from "@tanstack/react-router";
import { Wordmark, ButtonLink } from "./primitives";

const NAV = [
  { label: "Platform", to: "/#platform" },
  { label: "Traces", to: "/#traces" },
  { label: "Evaluations", to: "/#evaluations" },
  { label: "RAG Analytics", to: "/#rag" },
  { label: "Docs", to: "/#docs" },
];

export function LandingHeader() {
  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-paper/85 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-[1320px] items-center justify-between px-6">
        <Wordmark />
        <nav className="hidden items-center gap-7 md:flex">
          {NAV.map((n) => (
            <a
              key={n.label}
              href={n.to}
              className="label-eyebrow hover:text-foreground transition-colors"
            >
              {n.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-2">
          <Link to="/app/dashboard" className="label-eyebrow hidden sm:inline hover:text-foreground">
            Sign in
          </Link>
          <ButtonLink to="/app/dashboard">Open App →</ButtonLink>
        </div>
      </div>
    </header>
  );
}