import type { OtelSpan } from "@/lib/api/user";
import {
  formatDurationMs,
  formatTimestamp,
  otelSpanKindLabel,
  otelStatusLabel,
  otelStatusTone,
} from "@/lib/otel/format";
import { formatJsonValue, isEmptyList, isEmptyRecord } from "@/lib/otel/json";
import { Eyebrow, StatusBadge } from "@/components/helios/primitives";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-rule bg-card">
      <div className="border-b border-rule px-4 py-2.5">
        <Eyebrow>{title}</Eyebrow>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function Kv({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[110px_1fr] gap-2 py-1 text-[12.5px]">
      <dt className="label-eyebrow">{label}</dt>
      <dd className="font-mono break-all text-foreground">{value}</dd>
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all font-mono text-[11.5px] leading-relaxed text-foreground">
      {formatJsonValue(value as never)}
    </pre>
  );
}

function EmptyNote() {
  return <p className="text-[13px] text-muted-foreground">No data recorded</p>;
}

export function SpanInspector({ span }: { span: OtelSpan | null }) {
  if (!span) {
    return (
      <Section title="Span inspector">
        <p className="text-[13px] text-muted-foreground">Select a span in the timeline.</p>
      </Section>
    );
  }

  const scopeLabel = [span.scope_name, span.scope_version].filter(Boolean).join(" · ") || null;

  return (
    <div className="space-y-6">
      <Section title="Selected span">
        <dl>
          <Kv label="Name" value={span.name} />
          <Kv label="Span ID" value={span.span_id} />
          <Kv label="Parent ID" value={span.parent_span_id ?? "—"} />
          <Kv label="Kind" value={otelSpanKindLabel(span.kind)} />
          <Kv
            label="Status"
            value={
              <StatusBadge tone={otelStatusTone(span.status_code)}>
                {otelStatusLabel(span.status_code)}
              </StatusBadge>
            }
          />
          {span.status_message ? <Kv label="Message" value={span.status_message} /> : null}
          <Kv label="Start" value={formatTimestamp(span.start_time)} />
          <Kv label="End" value={formatTimestamp(span.end_time)} />
          <Kv label="Duration" value={formatDurationMs(span.duration_ms)} />
          {scopeLabel ? <Kv label="Scope" value={scopeLabel} /> : null}
          {span.trace_state ? <Kv label="Trace state" value={span.trace_state} /> : null}
          <Kv label="Flags" value={String(span.trace_flags)} />
        </dl>
      </Section>

      {!isEmptyRecord(span.resource_attributes) ? (
        <Section title="Resource attributes">
          <JsonBlock value={span.resource_attributes} />
        </Section>
      ) : (
        <Section title="Resource attributes">
          <EmptyNote />
        </Section>
      )}

      {!isEmptyRecord(span.scope_attributes) ? (
        <Section title="Scope attributes">
          <JsonBlock value={span.scope_attributes} />
        </Section>
      ) : null}

      {!isEmptyRecord(span.attributes) ? (
        <Section title="Span attributes">
          <JsonBlock value={span.attributes} />
        </Section>
      ) : (
        <Section title="Span attributes">
          <EmptyNote />
        </Section>
      )}

      {!isEmptyList(span.events) ? (
        <Section title={`Events · ${span.events.length}`}>
          <JsonBlock value={span.events} />
        </Section>
      ) : (
        <Section title="Events">
          <EmptyNote />
        </Section>
      )}

      {!isEmptyList(span.links) ? (
        <Section title={`Links · ${span.links.length}`}>
          <JsonBlock value={span.links} />
        </Section>
      ) : null}

      {(span.dropped_attributes_count > 0 ||
        span.dropped_events_count > 0 ||
        span.dropped_links_count > 0) && (
        <Section title="Dropped counts">
          <dl>
            <Kv label="Attributes" value={String(span.dropped_attributes_count)} />
            <Kv label="Events" value={String(span.dropped_events_count)} />
            <Kv label="Links" value={String(span.dropped_links_count)} />
          </dl>
        </Section>
      )}
    </div>
  );
}
