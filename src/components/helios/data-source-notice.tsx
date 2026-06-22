import { Eyebrow } from "@/components/helios/primitives";
import type { DataSource } from "@/hooks/use-traces";

export function DataSourceNotice({ source }: { source: DataSource }) {
  if (source !== "fallback") return null;
  return (
    <div className="mb-4 border border-rule bg-paper-2 px-3 py-2">
      <Eyebrow>Demo fallback · backend unavailable</Eyebrow>
    </div>
  );
}
