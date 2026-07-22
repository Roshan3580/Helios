/**
 * Semantic-convention attribute names and typed attribute builders.
 *
 * Uses OpenTelemetry GenAI convention keys that the Helios backend already
 * recognizes (`gen_ai.request.model` → `gen_ai.response.model` precedence,
 * numeric `gen_ai.usage.*` tokens) plus the one Helios categorization
 * attribute (`helios.span.type`) shared with the Python SDK. Builders never
 * fabricate values: undefined/malformed inputs are omitted, token counts must
 * be finite non-negative numbers, and no prompt/response/tool content or cost
 * field is ever produced.
 */

import type { Attributes, AttributeValue } from "@opentelemetry/api";
import { SpanKind } from "@opentelemetry/api";

// Helios categorization (namespaced; identical to the Python SDK).
export const HELIOS_SPAN_TYPE = "helios.span.type";

// GenAI semantic conventions (set only when the caller supplies a value).
export const GEN_AI_OPERATION_NAME = "gen_ai.operation.name";
export const GEN_AI_SYSTEM = "gen_ai.system";
export const GEN_AI_REQUEST_MODEL = "gen_ai.request.model";
export const GEN_AI_RESPONSE_MODEL = "gen_ai.response.model";
export const GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens";
export const GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens";
export const GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons";
export const GEN_AI_RESPONSE_ID = "gen_ai.response.id";
export const GEN_AI_AGENT_NAME = "gen_ai.agent.name";

// Tool / retrieval keys (aligned with the Python SDK and console).
export const TOOL_NAME = "tool.name";
export const RETRIEVAL_DOCUMENT_COUNT = "retrieval.document_count";
export const RETRIEVAL_SOURCE = "retrieval.source";

// Helios workflow metadata (namespaced; no standard OTel equivalent).
export const HELIOS_WORKFLOW_STEP = "helios.workflow.step";
export const HELIOS_WORKFLOW_RUN_ID = "helios.workflow.run_id";

/** Canonical `helios.span.type` values recognized by the backend and console. */
export const SPAN_TYPES = {
  agent: "agent",
  retrieval: "retrieval",
  tool: "tool",
  llm: "llm",
  custom: "custom",
} as const;

export type HeliosSpanType = keyof typeof SPAN_TYPES;

/** Default OTel SpanKind per Helios span type (mirrors the Python SDK). */
export const SPAN_KIND_BY_TYPE: Record<HeliosSpanType, SpanKind> = {
  agent: SpanKind.INTERNAL,
  retrieval: SpanKind.CLIENT,
  tool: SpanKind.INTERNAL,
  llm: SpanKind.CLIENT,
  custom: SpanKind.INTERNAL,
};

const MAX_STRING_ATTRIBUTE_LENGTH = 4096;

function boundString(value: string): string {
  if (value.length <= MAX_STRING_ATTRIBUTE_LENGTH) return value;
  return value.slice(0, MAX_STRING_ATTRIBUTE_LENGTH);
}

function isScalar(value: unknown): value is string | number | boolean {
  return (
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  );
}

/**
 * Keep only valid OTel attribute values: finite numbers, booleans, bounded
 * strings, and homogeneous scalar arrays. Everything else (null, undefined,
 * NaN/Infinity, objects, functions, mixed arrays) is dropped — never
 * stringified, so accidental object payloads cannot leak content.
 */
export function normalizeAttributes(attributes: Attributes | undefined): Attributes {
  if (!attributes) return {};
  const out: Attributes = {};
  for (const [key, value] of Object.entries(attributes)) {
    if (typeof key !== "string" || key.length === 0) continue;
    if (value === undefined || value === null) continue;
    if (typeof value === "string") {
      out[key] = boundString(value);
    } else if (isScalar(value)) {
      out[key] = value;
    } else if (Array.isArray(value) && value.length > 0 && value.every(isScalar)) {
      const first = typeof value[0];
      if (value.every((item) => typeof item === first)) {
        out[key] = value.map((item) =>
          typeof item === "string" ? boundString(item) : item,
        ) as AttributeValue;
      }
    }
  }
  return out;
}

/** A token count must be a finite, non-negative number; otherwise omitted. */
function normalizeTokenCount(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0) {
    return undefined;
  }
  return Math.floor(value);
}

function setString(out: Attributes, key: string, value: string | undefined): void {
  if (typeof value === "string" && value.trim().length > 0) {
    out[key] = boundString(value.trim());
  }
}

export interface LlmAttributeOptions {
  /** GenAI operation, e.g. "chat" → gen_ai.operation.name */
  operation?: string;
  /** Requested model → gen_ai.request.model (backend precedence: request first) */
  requestModel?: string;
  /** Model reported in the response → gen_ai.response.model */
  responseModel?: string;
  /** Provider/system, e.g. "openai" → gen_ai.system */
  provider?: string;
  /** Recorded input token count → gen_ai.usage.input_tokens (numeric only) */
  inputTokens?: number;
  /** Recorded output token count → gen_ai.usage.output_tokens (numeric only) */
  outputTokens?: number;
  /** Finish reasons → gen_ai.response.finish_reasons */
  finishReasons?: string[];
  /** Provider response ID → gen_ai.response.id (never a secret) */
  responseId?: string;
}

/** Attributes for an LLM/model span. Never includes prompts, completions, or cost. */
export function llmAttributes(options: LlmAttributeOptions): Attributes {
  const out: Attributes = {};
  setString(out, GEN_AI_OPERATION_NAME, options.operation);
  setString(out, GEN_AI_REQUEST_MODEL, options.requestModel);
  setString(out, GEN_AI_RESPONSE_MODEL, options.responseModel);
  setString(out, GEN_AI_SYSTEM, options.provider);
  const input = normalizeTokenCount(options.inputTokens);
  if (input !== undefined) out[GEN_AI_USAGE_INPUT_TOKENS] = input;
  const output = normalizeTokenCount(options.outputTokens);
  if (output !== undefined) out[GEN_AI_USAGE_OUTPUT_TOKENS] = output;
  if (
    Array.isArray(options.finishReasons) &&
    options.finishReasons.length > 0 &&
    options.finishReasons.every((reason) => typeof reason === "string")
  ) {
    out[GEN_AI_RESPONSE_FINISH_REASONS] = options.finishReasons.map(boundString);
  }
  setString(out, GEN_AI_RESPONSE_ID, options.responseId);
  return out;
}

export interface ToolAttributeOptions {
  /** Tool identity → tool.name */
  toolName?: string;
  /** Operation label, e.g. "execute_tool" → gen_ai.operation.name */
  operation?: string;
}

/** Attributes for a tool span. Tool arguments/results are never included. */
export function toolAttributes(options: ToolAttributeOptions): Attributes {
  const out: Attributes = {};
  setString(out, TOOL_NAME, options.toolName);
  setString(out, GEN_AI_OPERATION_NAME, options.operation);
  return out;
}

export interface RetrievalAttributeOptions {
  /** Operation label, e.g. "search" → gen_ai.operation.name */
  operation?: string;
  /** Number of documents returned → retrieval.document_count (numeric only) */
  documentCount?: number;
  /** Safe source category (e.g. "vector-store") → retrieval.source */
  source?: string;
}

/** Attributes for a retrieval span. Document content is never included. */
export function retrievalAttributes(options: RetrievalAttributeOptions): Attributes {
  const out: Attributes = {};
  setString(out, GEN_AI_OPERATION_NAME, options.operation);
  const count = normalizeTokenCount(options.documentCount);
  if (count !== undefined) out[RETRIEVAL_DOCUMENT_COUNT] = count;
  setString(out, RETRIEVAL_SOURCE, options.source);
  return out;
}

export interface WorkflowAttributeOptions {
  /** Workflow/agent identity → gen_ai.agent.name */
  agentName?: string;
  /** Step label → helios.workflow.step */
  stepName?: string;
  /** Caller-supplied non-secret run identifier → helios.workflow.run_id */
  runId?: string;
}

/** Attributes for a workflow/agent span. */
export function workflowAttributes(options: WorkflowAttributeOptions): Attributes {
  const out: Attributes = {};
  setString(out, GEN_AI_AGENT_NAME, options.agentName);
  setString(out, HELIOS_WORKFLOW_STEP, options.stepName);
  setString(out, HELIOS_WORKFLOW_RUN_ID, options.runId);
  return out;
}
