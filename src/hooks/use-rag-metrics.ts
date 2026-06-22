import { useEffect, useState } from "react";

import type { DataSource } from "@/hooks/data-source";
import { IS_DEMO_MODE } from "@/lib/api/client";
import { mapRagMetrics, type RagViewModel } from "@/lib/api/mappers";
import { fetchRagMetrics } from "@/lib/api/rag";

export interface RagMetricsLoadState {
  data: RagViewModel;
  source: DataSource;
  loading: boolean;
  error: string | null;
}

const DEMO_RAG: RagViewModel = {
  metrics: [
    { l: "Retrieval hit rate", v: "92.8%", d: "+1.2% wk" },
    { l: "Citation coverage", v: "84.1%", d: "+3.4% wk" },
    { l: "Missing-source rate", v: "5.6%", d: "−0.8% wk" },
    { l: "Reranker uplift", v: "+11.4 pts", d: "vs. baseline" },
  ],
  chunks: [
    { c: "policy-q3.md#§4.2", hit: 142, score: 0.92, tone: "success" },
    { c: "finance-handbook.md#§3", hit: 98, score: 0.81, tone: "success" },
    { c: "changelog/2025-q3.md", hit: 64, score: 0.76, tone: "warn" },
    { c: "security/keys.md", hit: 41, score: 0.69, tone: "warn" },
    { c: "legal/soc2.md", hit: 12, score: 0.51, tone: "danger" },
  ],
  failing: [
    "what is the refund window for annual plans?",
    "how do i rotate api keys without downtime?",
    "is there a soc2 type ii report available?",
    "can i export traces to datadog?",
    "how does helios store our prompts?",
  ],
};

export function useRagMetrics(): RagMetricsLoadState {
  const [state, setState] = useState<RagMetricsLoadState>({
    data: DEMO_RAG,
    source: IS_DEMO_MODE ? "demo" : "api",
    loading: !IS_DEMO_MODE,
    error: null,
  });

  useEffect(() => {
    if (IS_DEMO_MODE) {
      setState({ data: DEMO_RAG, source: "demo", loading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const metrics = await fetchRagMetrics("acme");
        if (cancelled) return;
        setState({
          data: mapRagMetrics(metrics),
          source: "api",
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          data: DEMO_RAG,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load RAG metrics",
        });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}
