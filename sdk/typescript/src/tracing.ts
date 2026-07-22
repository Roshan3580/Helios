/**
 * Manual tracing helpers over the OpenTelemetry API.
 *
 * Callbacks may be synchronous or asynchronous; the return value is
 * preserved, thrown errors / rejections are recorded on the span with ERROR
 * status and rethrown unwrapped, the span is ended exactly once, and the
 * active context propagates to nested spans and awaited work.
 */

import {
  context,
  ROOT_CONTEXT,
  SpanStatusCode,
  trace as otelTrace,
  type Attributes,
  type Span,
  type SpanKind,
  type Tracer,
} from "@opentelemetry/api";
import {
  HELIOS_SPAN_TYPE,
  SPAN_KIND_BY_TYPE,
  SPAN_TYPES,
  normalizeAttributes,
  type HeliosSpanType,
} from "./semconv.js";
import { HeliosConfigurationError } from "./errors.js";

export type SpanCallback<T> = (span: Span) => T;

export interface HeliosSpanOptions {
  /** Canonical Helios span type (`agent`/`retrieval`/`tool`/`llm`/`custom`). */
  spanType?: HeliosSpanType;
  /** Additional OTel attributes (validated; invalid values dropped). */
  attributes?: Attributes;
  /** Override the default OTel SpanKind for the span type. */
  kind?: SpanKind;
  /** Start a new root trace instead of nesting under the active span. */
  root?: boolean;
}

function recordFailure(span: Span, error: unknown): void {
  if (error instanceof Error) {
    span.recordException(error);
    span.setStatus({ code: SpanStatusCode.ERROR, message: error.message });
  } else {
    const message = typeof error === "string" ? error : "non-Error thrown";
    span.recordException(new Error(message));
    span.setStatus({ code: SpanStatusCode.ERROR, message });
  }
}

function isPromiseLike(value: unknown): value is PromiseLike<unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as PromiseLike<unknown>).then === "function"
  );
}

function validateSpanType(spanType: HeliosSpanType): void {
  if (!(spanType in SPAN_TYPES)) {
    throw new HeliosConfigurationError(
      `unknown spanType ${JSON.stringify(spanType)}; expected one of ` +
        Object.keys(SPAN_TYPES).join(", "),
    );
  }
}

/**
 * Run `fn` inside a started span. The span becomes the active span for the
 * duration of the callback (including awaited continuations) and is ended
 * exactly once, whether the callback returns a value, returns a promise, or
 * throws.
 */
export function runWithSpan<T>(
  tracer: Tracer,
  name: string,
  options: HeliosSpanOptions,
  fn: SpanCallback<T>,
): T {
  if (typeof name !== "string" || name.trim().length === 0) {
    throw new HeliosConfigurationError("span name must be a non-empty string");
  }
  if (typeof fn !== "function") {
    throw new HeliosConfigurationError("span callback must be a function");
  }
  const spanType = options.spanType ?? "custom";
  validateSpanType(spanType);

  const attributes = normalizeAttributes(options.attributes);
  attributes[HELIOS_SPAN_TYPE] = spanType;
  const kind = options.kind ?? SPAN_KIND_BY_TYPE[spanType];
  const parentContext = options.root ? ROOT_CONTEXT : context.active();

  return tracer.startActiveSpan(
    name,
    { kind, attributes },
    parentContext,
    (span: Span): T => {
      let ended = false;
      const endOnce = () => {
        if (!ended) {
          ended = true;
          span.end();
        }
      };
      try {
        const result = fn(span);
        if (isPromiseLike(result)) {
          return Promise.resolve(result).then(
            (value) => {
              endOnce();
              return value;
            },
            (error: unknown) => {
              recordFailure(span, error);
              endOnce();
              throw error;
            },
          ) as T;
        }
        endOnce();
        return result;
      } catch (error) {
        recordFailure(span, error);
        endOnce();
        throw error;
      }
    },
  );
}

/** The currently active OpenTelemetry span, if any. */
export function getActiveSpan(): Span | undefined {
  return otelTrace.getActiveSpan();
}
