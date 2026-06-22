import { useEffect, useState } from "react";

import { TRACES } from "@/components/helios/demo-data";
import type { DataSource } from "@/hooks/data-source";
import { IS_DEMO_MODE } from "@/lib/api/client";
import { fetchDashboardSummary } from "@/lib/api/dashboard";
import {
  mapDashboardSummary,
  mapFailingPrompts,
  type DashboardViewModel,
  type TraceListItem,
} from "@/lib/api/mappers";
import { fetchPrompts } from "@/lib/api/prompts";

export interface DashboardLoadState {
  data: DashboardViewModel;
  source: DataSource;
  loading: boolean;
  error: string | null;
}

const DEMO_RECENT_TRACES: TraceListItem[] = TRACES.slice(0, 6).map((trace) => ({
  id: trace.id,
  app: trace.app,
  query: trace.query,
  model: trace.model,
  lat: trace.lat,
  cost: trace.cost,
  tok: trace.tok,
  status: trace.status,
}));

const DEMO_DASHBOARD: DashboardViewModel = {
  metrics: [
    {
      label: "Total requests",
      value: "124,891",
      delta: { value: "+8.2%", tone: "up" },
      hint: "vs. previous 24h",
    },
    {
      label: "Avg latency",
      value: "1.34s",
      delta: { value: "−110ms", tone: "up" },
      hint: "p50 across models",
    },
    {
      label: "Token usage",
      value: "48.2M",
      delta: { value: "+3.1%", tone: "neutral" },
      hint: "prompt + completion",
    },
    {
      label: "Estimated cost",
      value: "$ 612.40",
      delta: { value: "+4.4%", tone: "down" },
      hint: "USD · all envs",
    },
    {
      label: "Error rate",
      value: "1.8%",
      delta: { value: "−0.4 pts", tone: "up" },
      hint: "5xx + tool failures",
    },
    {
      label: "Eval pass rate",
      value: "88.1%",
      delta: { value: "+3.4 pts", tone: "up" },
      hint: "support_qa.v4",
    },
    {
      label: "Citation coverage",
      value: "84.1%",
      delta: { value: "+1.2 pts", tone: "up" },
      hint: "rag.knowledge_base",
    },
    { label: "Active models", value: "3", hint: "gpt-4o · claude-3.5 · gemini-1.5" },
  ],
  recentTraces: DEMO_RECENT_TRACES,
  failingPrompts: [
    ["support.router.system / v5", "12 errs"],
    ["rag.answer.synth / v7", "8 errs"],
    ["router.classify.intent / v3", "3 errs"],
  ],
  modelUsage: [
    ["gpt-4o", 62],
    ["claude-3.5-sonnet", 26],
    ["gemini-1.5-pro", 9],
    ["gpt-4o-mini", 3],
  ],
};

export function useDashboardSummary(): DashboardLoadState {
  const [state, setState] = useState<DashboardLoadState>({
    data: IS_DEMO_MODE ? DEMO_DASHBOARD : DEMO_DASHBOARD,
    source: IS_DEMO_MODE ? "demo" : "api",
    loading: !IS_DEMO_MODE,
    error: null,
  });

  useEffect(() => {
    if (IS_DEMO_MODE) {
      setState({ data: DEMO_DASHBOARD, source: "demo", loading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const [summary, prompts] = await Promise.all([
          fetchDashboardSummary("acme"),
          fetchPrompts("acme"),
        ]);
        if (cancelled) return;
        const data = mapDashboardSummary(summary);
        data.failingPrompts = mapFailingPrompts(prompts);
        setState({ data, source: "api", loading: false, error: null });
      } catch (error) {
        if (cancelled) return;
        setState({
          data: DEMO_DASHBOARD,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load dashboard",
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
