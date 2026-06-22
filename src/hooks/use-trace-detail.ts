import { useEffect, useState } from "react";

import { IS_DEMO_MODE } from "@/lib/api/client";
import { mapBackendTraceDetail, type TraceDetailItem } from "@/lib/api/mappers";
import { fetchTraceDetail } from "@/lib/api/traces";
import { TRACES } from "@/components/helios/demo-data";

import type { DataSource } from "./use-traces";

const DEMO_SPANS = [
  {
    id: "demo_input",
    name: "user.query",
    kind: "INPUT",
    ms: 0,
    dur: 6,
    depth: 0,
    status: "success" as const,
  },
  {
    id: "demo_rag",
    name: "retriever.pgvector",
    kind: "RAG",
    ms: 12,
    dur: 184,
    depth: 1,
    status: "success" as const,
  },
  {
    id: "demo_rerank",
    name: "reranker.cohere",
    kind: "RAG",
    ms: 198,
    dur: 142,
    depth: 1,
    status: "success" as const,
  },
  {
    id: "demo_llm",
    name: "llm.openai.gpt-4o",
    kind: "LLM",
    ms: 342,
    dur: 812,
    depth: 1,
    status: "success" as const,
  },
  {
    id: "demo_tool",
    name: "tool.lookup_policy",
    kind: "TOOL",
    ms: 1160,
    dur: 198,
    depth: 2,
    status: "error" as const,
  },
  {
    id: "demo_output",
    name: "llm.openai.finalize",
    kind: "LLM",
    ms: 1370,
    dur: 52,
    depth: 1,
    status: "success" as const,
  },
];

function toDemoDetail(trace: (typeof TRACES)[number]): TraceDetailItem {
  return {
    id: trace.id,
    app: trace.app,
    query: trace.query,
    model: trace.model,
    lat: trace.lat,
    cost: trace.cost,
    tok: trace.tok,
    status: trace.status,
    spans: DEMO_SPANS,
  };
}

export interface TraceDetailLoadState {
  trace: TraceDetailItem | null;
  source: DataSource;
  loading: boolean;
  error: string | null;
}

export function useTraceDetail(traceId: string): TraceDetailLoadState {
  const demoTrace = TRACES.find((trace) => trace.id === traceId);

  const [state, setState] = useState<TraceDetailLoadState>(() => {
    if (IS_DEMO_MODE) {
      return {
        trace: demoTrace ? toDemoDetail(demoTrace) : null,
        source: "demo",
        loading: false,
        error: null,
      };
    }
    return { trace: null, source: "api", loading: true, error: null };
  });

  useEffect(() => {
    if (IS_DEMO_MODE) {
      setState({
        trace: demoTrace ? toDemoDetail(demoTrace) : null,
        source: "demo",
        loading: false,
        error: null,
      });
      return;
    }

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const detail = await fetchTraceDetail(traceId);
        if (cancelled) return;
        setState({
          trace: mapBackendTraceDetail(detail),
          source: "api",
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        const fallback = demoTrace ? toDemoDetail(demoTrace) : null;
        setState({
          trace: fallback,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load trace",
        });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [traceId, demoTrace]);

  return state;
}

export function timelineTotalMs(spans: TraceDetailItem["spans"]): number {
  if (!spans.length) return 1;
  return Math.max(...spans.map((span) => span.ms + span.dur), 1);
}
