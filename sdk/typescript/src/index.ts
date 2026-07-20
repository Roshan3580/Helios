/**
 * Helios OpenTelemetry SDK for Node.js.
 *
 * Server-side only (no browser support). Importing this module has no side
 * effects: nothing is registered, patched, or exported until
 * `Helios.configure()` is called.
 */

export { Helios } from "./runtime.js";
export { HeliosConfigurationError, HeliosInstrumentationError } from "./errors.js";
export {
  DEFAULT_ENDPOINT,
  DEFAULT_TIMEOUT_MILLIS,
  TRACES_PATH,
  normalizeEndpoint,
  type DiagnosticsLevel,
  type HeliosBatchOptions,
  type HeliosConfigureOptions,
  type HeliosInstrumentationOptions,
} from "./config.js";
export {
  HELIOS_SPAN_TYPE,
  SPAN_TYPES,
  llmAttributes,
  retrievalAttributes,
  toolAttributes,
  workflowAttributes,
  type HeliosSpanType,
  type LlmAttributeOptions,
  type RetrievalAttributeOptions,
  type ToolAttributeOptions,
  type WorkflowAttributeOptions,
} from "./semconv.js";
export { getActiveSpan, type HeliosSpanOptions, type SpanCallback } from "./tracing.js";
export { SDK_NAME, SDK_VERSION } from "./version.js";

// Re-export commonly needed OpenTelemetry API types so basic consumers don't
// have to add @opentelemetry/api themselves.
export { SpanKind, SpanStatusCode, type Attributes, type Span } from "@opentelemetry/api";
