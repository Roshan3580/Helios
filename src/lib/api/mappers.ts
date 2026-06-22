import type { BackendSpan, BackendSpanStatus, BackendTrace, BackendTraceStatus } from "./types";

export type FrontendTraceStatus = "success" | "warn" | "error";

export interface TraceListItem {
  id: string;
  app: string;
  query: string;
  model: string;
  lat: number;
  cost: number;
  tok: number;
  status: FrontendTraceStatus;
  createdAt?: string;
  promptTokens?: number;
  completionTokens?: number;
}

export interface TimelineSpan {
  id: string;
  name: string;
  kind: string;
  ms: number;
  dur: number;
  depth: number;
  status: FrontendTraceStatus;
  provider?: string | null;
  model?: string | null;
  inputPreview?: string | null;
  outputPreview?: string | null;
  tokenCount?: number | null;
  costUsd?: number | null;
}

export interface TraceDetailItem extends TraceListItem {
  spans: TimelineSpan[];
}

export function mapBackendStatus(
  status: BackendTraceStatus | BackendSpanStatus,
): FrontendTraceStatus {
  if (status === "warning") return "warn";
  return status;
}

export function mapBackendTrace(trace: BackendTrace): TraceListItem {
  return {
    id: trace.trace_id,
    app: trace.app_name,
    query: trace.user_query,
    model: trace.model,
    lat: trace.latency_ms,
    cost: trace.estimated_cost_usd,
    tok: trace.total_tokens,
    status: mapBackendStatus(trace.status),
    createdAt: trace.created_at,
    promptTokens: trace.prompt_tokens,
    completionTokens: trace.completion_tokens,
  };
}

export function mapBackendSpans(spans: BackendSpan[]): TimelineSpan[] {
  if (spans.length === 0) return [];

  const bySpanId = new Map(spans.map((span) => [span.span_id, span]));
  const baseMs = Math.min(...spans.map((span) => new Date(span.started_at).getTime()));

  const depthCache = new Map<string, number>();
  const depthOf = (span: BackendSpan): number => {
    if (depthCache.has(span.span_id)) return depthCache.get(span.span_id)!;
    if (!span.parent_span_id || !bySpanId.has(span.parent_span_id)) {
      depthCache.set(span.span_id, 0);
      return 0;
    }
    const depth = depthOf(bySpanId.get(span.parent_span_id)!) + 1;
    depthCache.set(span.span_id, depth);
    return depth;
  };

  return spans
    .map((span) => {
      const startMs = new Date(span.started_at).getTime();
      return {
        id: span.span_id,
        name: span.name,
        kind: span.span_type.toUpperCase(),
        ms: Math.max(0, startMs - baseMs),
        dur: span.latency_ms,
        depth: depthOf(span),
        status: mapBackendStatus(span.status),
        provider: span.provider,
        model: span.model,
        inputPreview: span.input_preview,
        outputPreview: span.output_preview,
        tokenCount: span.token_count,
        costUsd: span.cost_usd,
      };
    })
    .sort((a, b) => a.ms - b.ms);
}

export function mapBackendTraceDetail(
  trace: BackendTrace & { spans: BackendSpan[] },
): TraceDetailItem {
  return {
    ...mapBackendTrace(trace),
    spans: mapBackendSpans(trace.spans),
  };
}

/** Map frontend filter status back to backend query param. */
export function toBackendStatusFilter(status: FrontendTraceStatus): string {
  return status === "warn" ? "warning" : status;
}
