/** Pure helpers for OTel trace presentation (no React, no network). */

/** Format a duration that the backend already expresses in milliseconds. */
export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return "—";
  if (ms < 1) return `${(ms * 1000).toFixed(0)}µs`;
  if (ms < 1000) return `${ms < 10 ? ms.toFixed(2) : ms.toFixed(ms < 100 ? 1 : 0)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = ((ms % 60_000) / 1000).toFixed(1);
  return `${minutes}m ${seconds}s`;
}

/** Format a rate in [0, 1] as a percentage without misleading decimal noise. */
export function formatPercent(rate: number | null | undefined): string {
  if (rate == null || !Number.isFinite(rate)) return "—";
  const pct = rate * 100;
  if (pct === 0) return "0%";
  if (pct < 0.1) return "<0.1%";
  if (pct < 10) return `${pct.toFixed(1)}%`;
  return `${pct.toFixed(pct < 100 && pct % 1 !== 0 ? 1 : 0)}%`;
}

/** Compact integer formatting for counts and token totals. */
export function formatInteger(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return Math.round(value).toLocaleString();
}

/** Token totals: show a truthful empty label when no spans carried token attrs. */
export function formatTokenTotal(totalTokens: number, spansWithTokenData: number): string {
  if (spansWithTokenData <= 0) return "No token data";
  return formatInteger(totalTokens);
}

/** Shorten a 32-char hex OTel trace ID for list display. */
export function shortTraceId(traceId: string): string {
  if (traceId.length <= 12) return traceId;
  return `${traceId.slice(0, 8)}…${traceId.slice(-4)}`;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** OTel SpanKind wire values (UNSPECIFIED..CONSUMER). */
const SPAN_KIND_LABELS: Record<number, string> = {
  0: "UNSPECIFIED",
  1: "INTERNAL",
  2: "SERVER",
  3: "CLIENT",
  4: "PRODUCER",
  5: "CONSUMER",
};

export function otelSpanKindLabel(kind: number): string {
  return SPAN_KIND_LABELS[kind] ?? `KIND_${kind}`;
}

/** OTel StatusCode: UNSET=0, OK=1, ERROR=2. */
export function otelStatusLabel(statusCode: number): string {
  if (statusCode === 2) return "ERROR";
  if (statusCode === 1) return "OK";
  return "UNSET";
}

export function otelStatusTone(statusCode: number): "danger" | "success" | "neutral" {
  if (statusCode === 2) return "danger";
  if (statusCode === 1) return "success";
  return "neutral";
}

export function isOtelErrorStatus(statusCode: number): boolean {
  return statusCode === 2;
}
