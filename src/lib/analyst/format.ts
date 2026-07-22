/**
 * Pure presentation helpers for deterministic trace-analysis results.
 *
 * Labels only — no thresholds, no business logic, no severity overrides, and
 * no claims beyond the factual statements the backend returned. Unknown
 * future rule IDs fall back to the raw ID.
 */

import type { AnalysisFinding, OtelJsonValue } from "@/lib/api/user";

const RULE_LABELS: Record<string, string> = {
  error_span: "Error span",
  failing_child_transition: "Failing child transition",
  latency_concentration: "Latency concentration",
  repeated_sibling_tool_calls: "Repeated sibling tool calls",
  repeated_sibling_model_calls: "Repeated sibling model calls",
  serial_sibling_operations: "Serial sibling operations",
  missing_genai_telemetry: "Missing GenAI telemetry",
  orphan_span_parent: "Orphan span parent",
  cyclic_span_hierarchy: "Cyclic span hierarchy",
};

export function ruleLabel(ruleId: string): string {
  return RULE_LABELS[ruleId] ?? ruleId;
}

export type FindingSeverity = AnalysisFinding["severity"];

const SEVERITY_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 };

export function severityRank(severity: string): number {
  return SEVERITY_ORDER[severity] ?? 3;
}

export function severityLabel(severity: string): string {
  if (severity === "error") return "Error";
  if (severity === "warning") return "Warning";
  if (severity === "info") return "Info";
  return severity;
}

export function severityTone(severity: string): "danger" | "warn" | "info" | "neutral" {
  if (severity === "error") return "danger";
  if (severity === "warning") return "warn";
  if (severity === "info") return "info";
  return "neutral";
}

export function confidenceLabel(confidence: string): string {
  if (confidence === "high") return "High confidence";
  if (confidence === "medium") return "Medium confidence";
  if (confidence === "low") return "Low confidence";
  return confidence;
}

export function categoryLabel(category: string): string {
  if (!category) return "—";
  return category.charAt(0).toUpperCase() + category.slice(1);
}

/** Count findings per severity, in fixed error → warning → info order. */
export function severitySummary(
  findings: AnalysisFinding[],
): { severity: FindingSeverity; count: number }[] {
  const counts = new Map<FindingSeverity, number>();
  for (const finding of findings) {
    counts.set(finding.severity, (counts.get(finding.severity) ?? 0) + 1);
  }
  return (["error", "warning", "info"] as const)
    .filter((severity) => (counts.get(severity) ?? 0) > 0)
    .map((severity) => ({ severity, count: counts.get(severity) ?? 0 }));
}

/**
 * Render an observed/baseline metric value compactly and safely.
 * Objects and arrays are serialized as bounded JSON — never interpreted.
 */
export function formatObservedValue(value: OtelJsonValue | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/\.?0+$/, "");
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  try {
    const text = JSON.stringify(value);
    return text.length > 120 ? `${text.slice(0, 119)}…` : text;
  } catch {
    return "—";
  }
}
