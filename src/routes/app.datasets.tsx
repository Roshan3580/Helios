import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/helios/app-shell";
import { DataSourceNotice } from "@/components/helios/data-source-notice";
import { DemoOnlyAction } from "@/components/helios/demo-only-action";
import { Eyebrow } from "@/components/helios/primitives";
import { useDatasets } from "@/hooks/use-datasets";

export const Route = createFileRoute("/app/datasets")({ component: DatasetsPage });

function DatasetsPage() {
  const { datasets, source, loading } = useDatasets();

  return (
    <div>
      <PageHeader
        eyebrow="Improve"
        title="Datasets"
        description="Curated examples that ground every evaluation. Import from production traces or upload JSONL."
        actions={<DemoOnlyAction>New dataset</DemoOnlyAction>}
      />
      <DataSourceNotice source={source} />
      <div className="border border-rule bg-card">
        <div className="grid grid-cols-12 border-b border-rule px-4 py-2.5 label-eyebrow">
          <div className="col-span-4">Name</div>
          <div className="col-span-2">Examples</div>
          <div className="col-span-3">Owner</div>
          <div className="col-span-3 text-right">Updated</div>
        </div>
        {loading ? (
          <div className="px-4 py-8 text-center">
            <Eyebrow>Loading datasets…</Eyebrow>
          </div>
        ) : (
          datasets.map((d) => (
            <div
              key={d.name}
              className="grid grid-cols-12 items-center border-b border-rule px-4 py-3 font-mono text-[12.5px]"
            >
              <div className="col-span-4">{d.name}</div>
              <div className="col-span-2 text-muted-foreground">{d.examples}</div>
              <div className="col-span-3 text-muted-foreground">{d.owner}</div>
              <div className="col-span-3 text-right text-muted-foreground">{d.updated}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
