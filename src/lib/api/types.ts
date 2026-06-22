/** Backend API response shapes (Phase 1 trace endpoints). */

export type BackendTraceStatus = "success" | "warning" | "error";

export type BackendSpanType = "input" | "rag" | "llm" | "tool" | "output" | "evaluator";

export type BackendSpanStatus = "success" | "warning" | "error";

export interface BackendTrace {
  id: string;
  trace_id: string;
  project_slug: string;
  user_query: string;
  app_name: string;
  model: string;
  status: BackendTraceStatus;
  latency_ms: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
}

export interface BackendSpan {
  id: string;
  span_id: string;
  parent_span_id: string | null;
  name: string;
  span_type: BackendSpanType;
  provider: string | null;
  model: string | null;
  latency_ms: number;
  token_count: number | null;
  cost_usd: number | null;
  status: BackendSpanStatus;
  input_preview: string | null;
  output_preview: string | null;
  metadata_json: Record<string, unknown>;
  started_at: string;
  ended_at: string;
}

export interface BackendTraceDetail extends BackendTrace {
  spans: BackendSpan[];
}

export interface TraceListParams {
  project_slug?: string;
  status?: string;
  model?: string;
  limit?: number;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
