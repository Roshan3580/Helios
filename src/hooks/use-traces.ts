import { useEffect, useState } from "react";

import { IS_DEMO_MODE } from "@/lib/api/client";
import { mapBackendTrace, type TraceListItem } from "@/lib/api/mappers";
import { fetchTraces } from "@/lib/api/traces";
import { TRACES } from "@/components/helios/demo-data";

import type { DataSource } from "@/hooks/data-source";

export interface TracesLoadState {
  traces: TraceListItem[];
  source: DataSource;
  loading: boolean;
  error: string | null;
}

const DEMO_TRACES: TraceListItem[] = TRACES.map((trace) => ({
  id: trace.id,
  app: trace.app,
  query: trace.query,
  model: trace.model,
  lat: trace.lat,
  cost: trace.cost,
  tok: trace.tok,
  status: trace.status,
}));

export function useTraceList(): TracesLoadState {
  const [state, setState] = useState<TracesLoadState>({
    traces: IS_DEMO_MODE ? DEMO_TRACES : [],
    source: IS_DEMO_MODE ? "demo" : "api",
    loading: !IS_DEMO_MODE,
    error: null,
  });

  useEffect(() => {
    if (IS_DEMO_MODE) return;

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const rows = await fetchTraces({ limit: 50 });
        if (cancelled) return;
        setState({
          traces: rows.map(mapBackendTrace),
          source: "api",
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          traces: DEMO_TRACES,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load traces",
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
