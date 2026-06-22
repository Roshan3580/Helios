import { useEffect, useState } from "react";

import { DATASETS } from "@/components/helios/demo-data";
import type { DataSource } from "@/hooks/data-source";
import { IS_DEMO_MODE } from "@/lib/api/client";
import { fetchDatasets } from "@/lib/api/datasets";
import { mapDatasets, type DatasetRow } from "@/lib/api/mappers";

export interface DatasetsLoadState {
  datasets: DatasetRow[];
  source: DataSource;
  loading: boolean;
  error: string | null;
}

const DEMO_DATASETS: DatasetRow[] = DATASETS.map((dataset) => ({
  name: dataset.name,
  examples: dataset.examples,
  owner: dataset.owner,
  updated: dataset.updated,
}));

export function useDatasets(): DatasetsLoadState {
  const [state, setState] = useState<DatasetsLoadState>({
    datasets: DEMO_DATASETS,
    source: IS_DEMO_MODE ? "demo" : "api",
    loading: !IS_DEMO_MODE,
    error: null,
  });

  useEffect(() => {
    if (IS_DEMO_MODE) {
      setState({ datasets: DEMO_DATASETS, source: "demo", loading: false, error: null });
      return;
    }

    let cancelled = false;

    async function load() {
      setState((prev) => ({ ...prev, loading: true, error: null }));
      try {
        const rows = await fetchDatasets("acme");
        if (cancelled) return;
        setState({
          datasets: mapDatasets(rows),
          source: "api",
          loading: false,
          error: null,
        });
      } catch (error) {
        if (cancelled) return;
        setState({
          datasets: DEMO_DATASETS,
          source: "fallback",
          loading: false,
          error: error instanceof Error ? error.message : "Failed to load datasets",
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
