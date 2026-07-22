/**
 * Pure presentation helpers for project-window analysis results.
 *
 * Labels only — no thresholds, no business logic, no severity overrides, and
 * no claims beyond the factual statements the backend returned. Unknown
 * future rule IDs fall back to the raw ID.
 */

import type { ProjectFinding } from "@/lib/api/user";

const PROJECT_RULE_LABELS: Record<string, string> = {
  service_error_rate_regression: "Service error-rate regression",
  service_latency_regression: "Service latency regression",
  model_latency_regression: "Model latency regression",
  model_token_usage_regression: "Model token-usage regression",
  trace_latency_outliers: "Trace latency outliers",
  recurring_error_cluster: "Recurring error cluster",
  genai_instrumentation_gap: "GenAI instrumentation gap",
  error_concentration_by_service: "Error concentration by service",
};

export function projectRuleLabel(ruleId: string): string {
  return PROJECT_RULE_LABELS[ruleId] ?? ruleId;
}

const ENTITY_TYPE_LABELS: Record<string, string> = {
  service: "Service",
  model: "Model",
  error_signature: "Error signature",
  instrumentation: "Instrumentation",
  project: "Project",
};

export function entityTypeLabel(entityType: string): string {
  return ENTITY_TYPE_LABELS[entityType] ?? entityType;
}

export type ProjectFindingSeverity = ProjectFinding["severity"];

/** Count findings per severity, in fixed error → warning → info order. */
export function projectSeveritySummary(
  findings: ProjectFinding[],
): { severity: ProjectFindingSeverity; count: number }[] {
  const counts = new Map<ProjectFindingSeverity, number>();
  for (const finding of findings) {
    counts.set(finding.severity, (counts.get(finding.severity) ?? 0) + 1);
  }
  return (["error", "warning", "info"] as const)
    .filter((severity) => (counts.get(severity) ?? 0) > 0)
    .map((severity) => ({ severity, count: counts.get(severity) ?? 0 }));
}

/** Human label for the sample_size map, e.g. "100 current traces". */
export function sampleSizeLabel(sampleSize: Record<string, number>): string {
  const parts = Object.entries(sampleSize).map(
    ([key, value]) => `${value.toLocaleString()} ${key.replaceAll("_", " ")}`,
  );
  return parts.join(" · ");
}

/** True when any example/candidate cap truncated supporting evidence. */
export function anyExamplesTruncated(bounds: {
  services_truncated: boolean;
  models_truncated: boolean;
  error_groups_truncated: boolean;
  error_span_candidates_truncated: boolean;
  findings_truncated: boolean;
}): boolean {
  return (
    bounds.services_truncated ||
    bounds.models_truncated ||
    bounds.error_groups_truncated ||
    bounds.error_span_candidates_truncated ||
    bounds.findings_truncated
  );
}
