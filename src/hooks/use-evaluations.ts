import { useEffect, useState } from "react";

import type { DataSource } from "@/hooks/data-source";
import { IS_DEMO_MODE } from "@/lib/api/client";
import { fetchEvaluations } from "@/lib/api/evaluations";
import { mapEvaluations, type EvaluationsViewModel } from "@/lib/api/mappers";

export interface EvaluationsLoadState {
  data: EvaluationsViewModel;
  source: DataSource;
  loading: boolean;
  error: string | null;
}

const DEMO_EVALUATIONS: EvaluationsViewModel = {
  suites: [
    {
      name: "support_qa.regression",
      dataset: "support_qa.v4",
      runs: 38,
      pass: 88.1,
      lat: "1.51s",
      cost: "$0.020",
    },
    {
      name: "research.summary.quality",
      dataset: "research_summaries.v2",
      runs: 14,
      pass: 91.4,
      lat: "1.78s",
      cost: "$0.015",
    },
    {
      name: "rag.citation.coverage",
      dataset: "policy_retrieval.v1",
      runs: 22,
      pass: 84.7,
      lat: "1.32s",
      cost: "$0.012",
    },
  ],
  compare: [
    { p: "prompt.v1", m: "gpt-4o", acc: 82.4, cost: 0.018, lat: 1.42, cite: 71, tone: "neutral" },
    { p: "prompt.v2", m: "gpt-4o", acc: 88.1, cost: 0.02, lat: 1.51, cite: 84, tone: "success" },
    {
      p: "prompt.v2",
      m: "claude-3.5",
      acc: 86.7,
      cost: 0.015,
      lat: 1.78,
      cite: 80,
      tone: "neutral",
    },
    { p: "prompt.v3", m: "gemini-1.5", acc: 79.3, cost: 0.009, lat: 0.94, cite: 62, tone: "warn" },
  ],
  compareLabel: "Model comparison · support_qa.v4",
  compareRunAt: "18s ago",
};

export function useEvaluations(): EvaluationsLoadState {
  const [state, setState] = useState<EvaluationsLoadState>({
    data: DEMO_EVALUATIONS,
    source: IS_DEMO_MODE ? "demo" : "api",
    loading: !IS_DEMO_MODE,
    error: null,
  });

  useEffect(() => {
    if (IS_DEMO_MODE) {
      setState({ data: DEMO_EVALUATIONS, source: "demo", loading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const runs = await fetchEvaluations("acme");
        if (cancelled) return;
        setState({
          data: mapEvaluations(runs),
          source: "api",
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          data: DEMO_EVALUATIONS,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load evaluations",
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
