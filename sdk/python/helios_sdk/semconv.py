"""Centralized semantic-convention attribute names for manual Helios spans.

Uses OpenTelemetry GenAI semantic-convention attribute names where applicable
so manual spans align with what the OpenAI auto-instrumentor emits. Helios adds
one namespaced categorization attribute (`helios.span.type`); it never
fabricates token, cost, model, prompt, response, or evaluation values — those
appear only when a caller sets them explicitly.
"""

from opentelemetry.trace import SpanKind

# Helios categorization (namespaced so it can't collide with OTel conventions).
HELIOS_SPAN_TYPE = "helios.span.type"

# GenAI semantic conventions (only set when the caller supplies a value).
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"

# Span type values used with HELIOS_SPAN_TYPE.
SPAN_TYPE_AGENT = "agent"
SPAN_TYPE_RETRIEVAL = "retrieval"
SPAN_TYPE_TOOL = "tool"
SPAN_TYPE_LLM = "llm"
SPAN_TYPE_CUSTOM = "custom"

# Default OTel SpanKind per helper (overridable by callers via the raw tracer).
SPAN_KIND_BY_TYPE = {
    SPAN_TYPE_AGENT: SpanKind.INTERNAL,
    SPAN_TYPE_RETRIEVAL: SpanKind.CLIENT,
    SPAN_TYPE_TOOL: SpanKind.INTERNAL,
    SPAN_TYPE_LLM: SpanKind.CLIENT,
    SPAN_TYPE_CUSTOM: SpanKind.INTERNAL,
}
