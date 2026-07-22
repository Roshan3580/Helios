import { Eyebrow } from "@/components/helios/primitives";
import type { DataSource } from "@/hooks/data-source";

export function DataSourceNotice({ source }: { source: DataSource }) {
  // Both non-live sources get a visible notice so seeded/sample numbers are
  // never mistaken for authenticated project telemetry. "api" (real v2 data)
  // renders nothing.
  if (source === "api") return null;
  const message =
    source === "fallback"
      ? "Demo fallback · backend unavailable · not live telemetry"
      : "Demo data · sample content, not live telemetry";
  return (
    <div className="mb-4 border border-rule bg-paper-2 px-3 py-2">
      <Eyebrow>{message}</Eyebrow>
    </div>
  );
}
