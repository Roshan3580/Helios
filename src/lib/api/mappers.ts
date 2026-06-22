import type {
  BackendDashboardSummary,
  BackendDatasetSummary,
  BackendEvaluationRun,
  BackendPromptVersion,
  BackendRagChunkMetric,
  BackendRagChunkStatus,
  BackendRagMetrics,
  BackendSpan,
  BackendSpanStatus,
  BackendTrace,
  BackendTraceStatus,
} from "./types";

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

// --- Phase 3 analytics mappers ---

export interface DashboardMetricCard {
  label: string;
  value: string;
  delta?: { value: string; tone: "up" | "down" | "neutral" };
  hint?: string;
}

export interface DashboardViewModel {
  metrics: DashboardMetricCard[];
  recentTraces: TraceListItem[];
  failingPrompts: [string, string][];
  modelUsage: [string, number][];
}

export interface RagMetricRow {
  l: string;
  v: string;
  d: string;
}

export interface RagChunkRow {
  c: string;
  hit: number;
  score: number;
  tone: "success" | "warn" | "danger";
}

export interface RagViewModel {
  metrics: RagMetricRow[];
  chunks: RagChunkRow[];
  failing: string[];
}

export interface EvalSuiteRow {
  name: string;
  dataset: string;
  runs: number;
  pass: number;
  lat: string;
  cost: string;
}

export interface EvalCompareRow {
  p: string;
  m: string;
  acc: number;
  cost: number;
  lat: number;
  cite: number;
  tone: "success" | "warn" | "neutral" | "danger";
}

export interface EvaluationsViewModel {
  suites: EvalSuiteRow[];
  compare: EvalCompareRow[];
  compareLabel: string;
  compareRunAt: string;
}

export interface PromptRow {
  name: string;
  versions: number;
  latest: string;
  model: string;
  score: number;
  lat: string;
  cost: string;
  updated: string;
}

export interface DatasetRow {
  name: string;
  examples: number;
  owner: string;
  updated: string;
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

function formatLatencySeconds(ms: number): string {
  return `${(ms / 1000).toFixed(2)}s`;
}

function formatPercent(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

function formatUsd(value: number, digits = 2): string {
  if (value >= 1) return `$ ${value.toFixed(digits)}`;
  return `$ ${value.toFixed(digits)}`;
}

function formatUsdCompact(value: number): string {
  return `$${value.toFixed(3)}`;
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const days = Math.floor(diffMs / 86_400_000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 7) return `${days}d ago`;
  return `${Math.floor(days / 7)}w ago`;
}

function mapRagChunkStatus(status: BackendRagChunkStatus): "success" | "warn" | "danger" {
  if (status === "ok") return "success";
  if (status === "drift") return "warn";
  return "danger";
}

function parseVersionNumber(version: string): number {
  const match = /^v(\d+)/i.exec(version);
  return match ? Number(match[1]) : 0;
}

const EVAL_SUITE_NAMES: Record<string, string> = {
  "support_qa.v4": "support_qa.regression",
  "research_summaries.v2": "research.summary.quality",
  "policy_retrieval.v1": "rag.citation.coverage",
};

const DATASET_OWNERS: Record<string, string> = {
  "support_qa.v4": "mm@helios.dev",
  "research_summaries.v2": "kr@helios.dev",
  "policy_retrieval.v1": "ai-team",
};

function evalCompareTone(acc: number): EvalCompareRow["tone"] {
  if (acc >= 88) return "success";
  if (acc >= 84) return "neutral";
  if (acc >= 79) return "warn";
  return "danger";
}

export function mapDashboardSummary(summary: BackendDashboardSummary): DashboardViewModel {
  const modelNames = summary.model_breakdown.map((item) => item.model).join(" · ");
  const metrics: DashboardMetricCard[] = [
    {
      label: "Total requests",
      value: formatCount(summary.total_requests),
      hint: "sample · seeded traces",
    },
    {
      label: "Avg latency",
      value: formatLatencySeconds(summary.avg_latency_ms),
      hint: "p50 across models",
    },
    {
      label: "Token usage",
      value: formatCount(summary.total_tokens),
      hint: "prompt + completion",
    },
    {
      label: "Estimated cost",
      value: formatUsd(summary.estimated_cost_usd),
      hint: "USD · sample data",
    },
    {
      label: "Error rate",
      value: formatPercent(summary.error_rate),
      hint: "5xx + tool failures",
    },
    {
      label: "Eval pass rate",
      value: summary.eval_pass_rate != null ? formatPercent(summary.eval_pass_rate) : "—",
      hint: "from eval runs",
    },
    {
      label: "Citation coverage",
      value: summary.citation_coverage != null ? formatPercent(summary.citation_coverage) : "—",
      hint: "from eval runs",
    },
    {
      label: "Active models",
      value: String(summary.model_breakdown.length),
      hint: modelNames || "no models",
    },
  ];

  return {
    metrics,
    recentTraces: summary.recent_traces.map(mapBackendTrace),
    failingPrompts: [],
    modelUsage: summary.model_breakdown.map(
      (item) => [item.model, Math.round(item.share_pct)] as [string, number],
    ),
  };
}

export function mapRagMetrics(metrics: BackendRagMetrics): RagViewModel {
  const okChunks = metrics.chunk_metrics.filter((chunk) => chunk.status === "ok");
  const weakChunks = metrics.chunk_metrics.filter((chunk) => chunk.status !== "ok");
  const okAvg =
    okChunks.length > 0
      ? okChunks.reduce((sum, chunk) => sum + chunk.quality_score, 0) / okChunks.length
      : 0;
  const weakAvg =
    weakChunks.length > 0
      ? weakChunks.reduce((sum, chunk) => sum + chunk.quality_score, 0) / weakChunks.length
      : 0;
  const rerankerUplift = okAvg > 0 ? (okAvg - weakAvg) * 100 : 0;

  return {
    metrics: [
      {
        l: "Retrieval hit rate",
        v: formatPercent(metrics.retrieval_hit_rate),
        d: "sample aggregate",
      },
      {
        l: "Citation coverage",
        v: formatPercent(metrics.citation_coverage),
        d: "from eval runs",
      },
      {
        l: "Missing-source rate",
        v: formatPercent(metrics.missing_source_rate),
        d: "RAG traces",
      },
      {
        l: "Reranker uplift",
        v: `+${rerankerUplift.toFixed(1)} pts`,
        d: "vs. low-quality chunks",
      },
    ],
    chunks: metrics.chunk_metrics.map(mapRagChunk),
    failing: metrics.top_failing_queries.map((query) => query.toLowerCase()),
  };
}

export function mapRagChunk(chunk: BackendRagChunkMetric): RagChunkRow {
  return {
    c: chunk.chunk_ref,
    hit: chunk.retrieval_hits,
    score: chunk.quality_score,
    tone: mapRagChunkStatus(chunk.status),
  };
}

export function mapEvaluations(runs: BackendEvaluationRun[]): EvaluationsViewModel {
  const suites = runs.map((run) => ({
    name: EVAL_SUITE_NAMES[run.dataset_name] ?? `${run.dataset_name}.suite`,
    dataset: run.dataset_name,
    runs: 1,
    pass: Math.round(run.accuracy * 1000) / 10,
    lat: formatLatencySeconds(run.latency_ms),
    cost: formatUsdCompact(run.cost_usd),
  }));

  const compare = runs.map((run) => ({
    p: `${run.prompt_name} · latest`,
    m: run.model,
    acc: Math.round(run.accuracy * 1000) / 10,
    cost: run.cost_usd,
    lat: run.latency_ms / 1000,
    cite: Math.round(run.citation_coverage * 100),
    tone: evalCompareTone(run.accuracy * 100),
  }));

  const primary = runs[0];
  return {
    suites,
    compare,
    compareLabel: primary ? `Model comparison · ${primary.dataset_name}` : "Model comparison",
    compareRunAt: primary ? formatRelative(primary.created_at) : "—",
  };
}

export function mapPromptVersions(versions: BackendPromptVersion[]): PromptRow[] {
  const grouped = new Map<string, BackendPromptVersion[]>();
  for (const version of versions) {
    const rows = grouped.get(version.name) ?? [];
    rows.push(version);
    grouped.set(version.name, rows);
  }

  return [...grouped.entries()]
    .map(([name, rows]) => {
      const sorted = [...rows].sort(
        (a, b) => parseVersionNumber(b.version) - parseVersionNumber(a.version),
      );
      const latest = sorted[0];
      return {
        name,
        versions: rows.length,
        latest: latest.version,
        model: latest.model,
        score: latest.eval_score ?? 0,
        lat: latest.latency_ms != null ? formatLatencySeconds(latest.latency_ms) : "—",
        cost: latest.cost_usd != null ? formatUsdCompact(latest.cost_usd) : "—",
        updated: formatRelative(latest.created_at),
      };
    })
    .sort((a, b) => a.name.localeCompare(b.name));
}

export function mapFailingPrompts(versions: BackendPromptVersion[]): [string, string][] {
  return mapPromptVersions(versions)
    .filter((prompt) => prompt.score < 85)
    .map((prompt) => [
      `${prompt.name} / ${prompt.latest}`,
      `${Math.round(100 - prompt.score)} errs`,
    ]);
}

export function mapDatasets(datasets: BackendDatasetSummary[]): DatasetRow[] {
  return datasets.map((dataset) => ({
    name: dataset.name,
    examples: dataset.total_cases,
    owner: DATASET_OWNERS[dataset.name] ?? "ai-team",
    updated: formatRelative(dataset.last_run_at),
  }));
}
