import { useEffect, useState } from "react";

import { PROMPTS } from "@/components/helios/demo-data";
import type { DataSource } from "@/hooks/data-source";
import { IS_DEMO_MODE } from "@/lib/api/client";
import { mapPromptVersions, type PromptRow } from "@/lib/api/mappers";
import { fetchPrompts } from "@/lib/api/prompts";

export interface PromptsLoadState {
  prompts: PromptRow[];
  source: DataSource;
  loading: boolean;
  error: string | null;
}

const DEMO_PROMPTS: PromptRow[] = PROMPTS.map((prompt) => ({
  name: prompt.name,
  versions: prompt.versions,
  latest: prompt.latest,
  model: prompt.model,
  score: prompt.score,
  lat: prompt.lat,
  cost: prompt.cost,
  updated: prompt.updated,
}));

export function usePrompts(): PromptsLoadState {
  const [state, setState] = useState<PromptsLoadState>({
    prompts: DEMO_PROMPTS,
    source: IS_DEMO_MODE ? "demo" : "api",
    loading: !IS_DEMO_MODE,
    error: null,
  });

  useEffect(() => {
    if (IS_DEMO_MODE) {
      setState({ prompts: DEMO_PROMPTS, source: "demo", loading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const versions = await fetchPrompts("acme");
        if (cancelled) return;
        setState({
          prompts: mapPromptVersions(versions),
          source: "api",
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          prompts: DEMO_PROMPTS,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load prompts",
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
