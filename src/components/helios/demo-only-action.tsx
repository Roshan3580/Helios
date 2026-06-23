import { useState, type ReactNode } from "react";

import { Eyebrow } from "@/components/helios/primitives";
import { cn } from "@/lib/utils";

export function DemoOnlyAction({
  children,
  variant = "primary",
}: {
  children: ReactNode;
  variant?: "primary" | "outline";
}) {
  const [open, setOpen] = useState(false);
  const base =
    "inline-flex items-center justify-center gap-2 px-4 h-10 text-sm font-medium transition-colors border cursor-pointer";
  const variants: Record<string, string> = {
    primary: "bg-ink text-paper border-ink hover:bg-ink-soft",
    outline: "bg-transparent text-ink border-ink/70 hover:bg-paper-2",
  };

  return (
    <div className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn(base, variants[variant])}
      >
        {children}
      </button>
      {open && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-40 cursor-default"
            aria-label="Close"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-50 mt-2 w-72 border border-rule bg-paper p-3 shadow-sm">
            <Eyebrow>Demo only</Eyebrow>
            <p className="mt-2 text-[13px] leading-relaxed text-muted-foreground">
              Creation workflow planned for a future phase. This portfolio MVP focuses on read paths
              and trace ingestion.
            </p>
          </div>
        </>
      )}
    </div>
  );
}
