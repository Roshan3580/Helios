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

export interface BackendModelBreakdown {
  model: string;
  count: number;
  share_pct: number;
}

export interface BackendStatusBreakdown {
  status: BackendTraceStatus;
  count: number;
  share_pct: number;
}

export interface BackendDashboardSummary {
  total_requests: number;
  avg_latency_ms: number;
  total_tokens: number;
  estimated_cost_usd: number;
  error_rate: number;
  eval_pass_rate: number | null;
  citation_coverage: number | null;
  active_projects: number;
  recent_trace_count: number;
  model_breakdown: BackendModelBreakdown[];
  status_breakdown: BackendStatusBreakdown[];
  recent_traces: BackendTrace[];
  demo: boolean;
}

export type BackendRagChunkStatus = "ok" | "drift" | "low";

export interface BackendRagChunkMetric {
  id: string;
  chunk_ref: string;
  retrieval_hits: number;
  quality_score: number;
  status: BackendRagChunkStatus;
  created_at: string;
}

export interface BackendRagMetrics {
  retrieval_hit_rate: number;
  citation_coverage: number;
  missing_source_rate: number;
  avg_chunk_quality: number;
  low_confidence_queries: string[];
  top_failing_queries: string[];
  chunk_metrics: BackendRagChunkMetric[];
  demo: boolean;
}

export interface BackendEvaluationRun {
  id: string;
  dataset_name: string;
  prompt_name: string;
  model: string;
  accuracy: number;
  citation_coverage: number;
  latency_ms: number;
  cost_usd: number;
  status: string;
  created_at: string;
}

export interface BackendPromptVersion {
  id: string;
  name: string;
  version: string;
  model: string;
  eval_score: number | null;
  latency_ms: number | null;
  cost_usd: number | null;
  created_at: string;
}

export interface BackendDatasetSummary {
  name: string;
  total_cases: number;
  passing_rate: number;
  last_run_at: string | null;
  linked_evaluation_count: number;
}
