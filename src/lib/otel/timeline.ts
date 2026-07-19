import type { OtelSpan } from "@/lib/api/user";

export interface TimelineRow {
  span: OtelSpan;
  /** Offset from the earliest span start, in ms. */
  offsetMs: number;
  durationMs: number;
  depth: number;
}

/**
 * Build waterfall rows sorted by start time with parent-derived depth.
 * Orphaned parent IDs are treated as roots (depth 0). Cycles are broken.
 */
export function buildTimelineRows(spans: OtelSpan[]): TimelineRow[] {
  if (spans.length === 0) return [];

  const byId = new Map(spans.map((span) => [span.span_id, span]));
  const baseMs = Math.min(...spans.map((span) => new Date(span.start_time).getTime()));

  const depthCache = new Map<string, number>();
  const visiting = new Set<string>();

  const depthOf = (span: OtelSpan): number => {
    if (depthCache.has(span.span_id)) return depthCache.get(span.span_id)!;
    if (visiting.has(span.span_id)) {
      depthCache.set(span.span_id, 0);
      return 0;
    }
    visiting.add(span.span_id);
    if (!span.parent_span_id || !byId.has(span.parent_span_id)) {
      depthCache.set(span.span_id, 0);
      visiting.delete(span.span_id);
      return 0;
    }
    const depth = depthOf(byId.get(span.parent_span_id)!) + 1;
    depthCache.set(span.span_id, depth);
    visiting.delete(span.span_id);
    return depth;
  };

  return spans
    .map((span) => {
      const startMs = new Date(span.start_time).getTime();
      return {
        span,
        offsetMs: Math.max(0, startMs - baseMs),
        durationMs: Math.max(0, span.duration_ms),
        depth: depthOf(span),
      };
    })
    .sort((a, b) => {
      if (a.offsetMs !== b.offsetMs) return a.offsetMs - b.offsetMs;
      return a.span.span_id.localeCompare(b.span.span_id);
    });
}

export function timelineTotalMs(rows: TimelineRow[]): number {
  if (rows.length === 0) return 1;
  return Math.max(...rows.map((row) => row.offsetMs + row.durationMs), 1);
}
