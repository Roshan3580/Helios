import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("label-eyebrow", className)}>{children}</div>;
}

export function SectionHeader({
  eyebrow,
  title,
  description,
  align = "left",
}: {
  eyebrow?: string;
  title: ReactNode;
  description?: ReactNode;
  align?: "left" | "center";
}) {
  return (
    <div className={cn("max-w-3xl", align === "center" && "mx-auto text-center")}>
      {eyebrow && <Eyebrow className="mb-4">{eyebrow}</Eyebrow>}
      <h2 className="font-serif text-4xl leading-[1.05] tracking-tight text-foreground md:text-5xl">
        {title}
      </h2>
      {description && (
        <p className="mt-5 max-w-2xl text-base leading-relaxed text-muted-foreground md:text-[17px]">
          {description}
        </p>
      )}
    </div>
  );
}

export function StatusBadge({
  tone = "neutral",
  children,
}: {
  tone?: "neutral" | "success" | "warn" | "danger" | "info";
  children: ReactNode;
}) {
  const toneMap: Record<string, string> = {
    neutral: "text-ink-soft bg-paper-2 border-rule",
    success:
      "text-[color:var(--accent-success)] bg-[color-mix(in_oklab,var(--accent-success)_10%,var(--paper))] border-[color-mix(in_oklab,var(--accent-success)_30%,var(--rule))]",
    warn: "text-[color:var(--accent-amber)] bg-[color-mix(in_oklab,var(--accent-amber)_10%,var(--paper))] border-[color-mix(in_oklab,var(--accent-amber)_30%,var(--rule))]",
    danger:
      "text-[color:var(--accent-danger)] bg-[color-mix(in_oklab,var(--accent-danger)_8%,var(--paper))] border-[color-mix(in_oklab,var(--accent-danger)_30%,var(--rule))]",
    info: "text-[color:var(--accent-indigo)] bg-[color-mix(in_oklab,var(--accent-indigo)_8%,var(--paper))] border-[color-mix(in_oklab,var(--accent-indigo)_30%,var(--rule))]",
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 border px-1.5 py-0.5 font-mono text-[10.5px] uppercase tracking-wider",
        toneMap[tone],
      )}
    >
      <span className="size-1 rounded-full bg-current" />
      {children}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  delta,
  hint,
}: {
  label: string;
  value: ReactNode;
  delta?: { value: string; tone?: "up" | "down" | "neutral" };
  hint?: string;
}) {
  const deltaColor =
    delta?.tone === "up"
      ? "text-[color:var(--accent-success)]"
      : delta?.tone === "down"
        ? "text-[color:var(--accent-danger)]"
        : "text-muted-foreground";
  return (
    <div className="group relative border border-rule bg-card p-5">
      <div className="label-eyebrow">{label}</div>
      <div className="mt-3 flex items-baseline justify-between gap-2">
        <div className="font-serif text-3xl leading-none tracking-tight">{value}</div>
        {delta && <div className={cn("font-mono text-xs", deltaColor)}>{delta.value}</div>}
      </div>
      {hint && <div className="mt-2 font-mono text-[11px] text-muted-foreground">{hint}</div>}
    </div>
  );
}

export function HeliosMark({ className }: { className?: string }) {
  return (
    <img
      src="/helios-logo.png"
      alt=""
      aria-hidden
      className={cn("size-5 object-contain", className)}
    />
  );
}

export function Wordmark({ to = "/", className }: { to?: string; className?: string }) {
  return (
    <Link to={to} className={cn("flex items-center gap-2 text-foreground", className)}>
      <HeliosMark />
      <span className="font-serif text-xl tracking-tight">Helios</span>
      <span className="label-eyebrow ml-1 hidden sm:inline">/ Observatory</span>
    </Link>
  );
}

export function ButtonLink({
  to,
  variant = "primary",
  children,
  className,
}: {
  to: string;
  variant?: "primary" | "ghost" | "outline";
  children: ReactNode;
  className?: string;
}) {
  const base =
    "inline-flex items-center justify-center gap-2 px-4 h-10 text-sm font-medium transition-colors border";
  const variants: Record<string, string> = {
    primary: "bg-ink text-paper border-ink hover:bg-ink-soft",
    outline: "bg-transparent text-ink border-ink/70 hover:bg-paper-2",
    ghost: "bg-transparent text-ink border-transparent hover:bg-paper-2",
  };
  return (
    <Link to={to} className={cn(base, variants[variant], className)}>
      {children}
    </Link>
  );
}
