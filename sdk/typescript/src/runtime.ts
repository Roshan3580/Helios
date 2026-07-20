/**
 * Helios Node runtime: OpenTelemetry provider ownership, canonical OTLP
 * export, optional instrumentation, and lifecycle.
 *
 * Importing this module never touches the OpenTelemetry global registry or
 * the network; only `Helios.configure()` does. `configure()` owns exactly one
 * NodeTracerProvider: identical repeated configuration is idempotent,
 * conflicting reconfiguration throws, reconfiguration is allowed only after
 * `shutdown()`, and a foreign global tracer provider is never replaced.
 */

import {
  context,
  propagation,
  trace as otelTrace,
  type Attributes,
  type Span,
  type Tracer,
} from "@opentelemetry/api";
import { AsyncLocalStorageContextManager } from "@opentelemetry/context-async-hooks";
import { CompositePropagator, W3CBaggagePropagator, W3CTraceContextPropagator } from "@opentelemetry/core";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-proto";
import { defaultResource, resourceFromAttributes } from "@opentelemetry/resources";
import { BatchSpanProcessor, NodeTracerProvider } from "@opentelemetry/sdk-trace-node";
import type { Instrumentation } from "@opentelemetry/instrumentation";

import {
  configSnapshot,
  resolveConfig,
  type HeliosConfigureOptions,
  type ResolvedHeliosConfig,
} from "./config.js";
import { diag } from "@opentelemetry/api";
import { applyDiagnostics, disableDiagnostics, redactDiagnosticText } from "./diagnostics.js";
import { HeliosConfigurationError, HeliosInstrumentationError } from "./errors.js";
import {
  getActiveSpan,
  runWithSpan,
  type HeliosSpanOptions,
  type SpanCallback,
} from "./tracing.js";
import { SDK_NAME, SDK_VERSION } from "./version.js";

const TRACER_NAME = "helios-sdk";

interface RuntimeState {
  snapshot: string;
  extraInstrumentations: unknown[];
  config: ResolvedHeliosConfig;
  provider: NodeTracerProvider;
  tracer: Tracer;
  contextManager: AsyncLocalStorageContextManager;
  ownsGlobalContextManager: boolean;
  ownsGlobalPropagator: boolean;
  unregisterInstrumentations: (() => void) | null;
  diagnosticsInstalled: boolean;
  shutdownPromise: Promise<void> | null;
}

let state: RuntimeState | null = null;

function requireConfigured(): RuntimeState {
  if (state === null) {
    throw new HeliosConfigurationError(
      "Helios is not configured; call Helios.configure() first",
    );
  }
  return state;
}

async function loadOpenAiInstrumentation(
  config: ResolvedHeliosConfig,
): Promise<Instrumentation> {
  let mod: Record<string, unknown>;
  try {
    mod = (await import("@opentelemetry/instrumentation-openai")) as Record<
      string,
      unknown
    >;
  } catch {
    throw new HeliosInstrumentationError(
      "OpenAI instrumentation requires the optional peer dependency. Install it with:\n" +
        "    npm install @opentelemetry/instrumentation-openai",
    );
  }
  const ctor = (mod["OpenAIInstrumentation"] ??
    (mod["default"] as Record<string, unknown> | undefined)?.[
      "OpenAIInstrumentation"
    ]) as
    | (new (config?: Record<string, unknown>) => Instrumentation & {
        setConfig(config: Record<string, unknown>): void;
        getConfig(): Record<string, unknown>;
      })
    | undefined;
  if (typeof ctor !== "function") {
    throw new HeliosInstrumentationError(
      "@opentelemetry/instrumentation-openai did not export OpenAIInstrumentation",
    );
  }
  const instrumentation = new ctor({ captureMessageContent: config.captureContent });
  // The upstream constructor lets OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT
  // override the passed config. Helios owns the privacy default, so force the
  // resolved value after construction (setConfig is not env-overridden).
  instrumentation.setConfig({
    ...instrumentation.getConfig(),
    captureMessageContent: config.captureContent,
  });
  return instrumentation;
}

async function loadNodeAutoInstrumentations(
  config: ResolvedHeliosConfig,
): Promise<Instrumentation[]> {
  let mod: Record<string, unknown>;
  try {
    mod = (await import("@opentelemetry/auto-instrumentations-node")) as Record<
      string,
      unknown
    >;
  } catch {
    throw new HeliosInstrumentationError(
      "Node auto-instrumentation requires the optional peer dependency. Install it with:\n" +
        "    npm install @opentelemetry/auto-instrumentations-node",
    );
  }
  const factory = (mod["getNodeAutoInstrumentations"] ??
    (mod["default"] as Record<string, unknown> | undefined)?.[
      "getNodeAutoInstrumentations"
    ]) as ((configs?: Record<string, { enabled?: boolean }>) => Instrumentation[]) | undefined;
  if (typeof factory !== "function") {
    throw new HeliosInstrumentationError(
      "@opentelemetry/auto-instrumentations-node did not export getNodeAutoInstrumentations",
    );
  }
  const overrides: Record<string, { enabled: boolean }> = {};
  if (typeof config.instrumentations.node === "object") {
    for (const name of config.instrumentations.node.disabledInstrumentations) {
      overrides[name] = { enabled: false };
    }
  }
  return factory(overrides);
}

async function buildInstrumentations(
  config: ResolvedHeliosConfig,
  extra: unknown[],
): Promise<Instrumentation[]> {
  const instrumentations: Instrumentation[] = [];
  if (config.instrumentations.node) {
    instrumentations.push(...(await loadNodeAutoInstrumentations(config)));
  }
  if (config.instrumentations.openai) {
    instrumentations.push(await loadOpenAiInstrumentation(config));
  }
  for (const candidate of extra) {
    if (
      typeof candidate !== "object" ||
      candidate === null ||
      typeof (candidate as Instrumentation).enable !== "function" ||
      typeof (candidate as Instrumentation).disable !== "function"
    ) {
      throw new HeliosConfigurationError(
        "extraInstrumentations entries must implement the OpenTelemetry Instrumentation interface",
      );
    }
    instrumentations.push(candidate as Instrumentation);
  }
  return instrumentations;
}

function buildResource(config: ResolvedHeliosConfig) {
  const attributes: Attributes = {
    ...config.resourceAttributes,
    "service.name": config.serviceName,
    "helios.sdk.name": SDK_NAME,
    "helios.sdk.version": SDK_VERSION,
  };
  if (config.serviceVersion) attributes["service.version"] = config.serviceVersion;
  if (config.environment) {
    attributes["deployment.environment.name"] = config.environment;
  }
  return defaultResource().merge(resourceFromAttributes(attributes));
}

async function configure(options: HeliosConfigureOptions = {}): Promise<void> {
  const config = resolveConfig(options);
  const snapshot = configSnapshot(config);
  const extra = [...config.extraInstrumentations];

  if (state !== null) {
    const sameExtra =
      state.extraInstrumentations.length === extra.length &&
      state.extraInstrumentations.every((item, index) => item === extra[index]);
    if (state.snapshot === snapshot && sameExtra) {
      return; // identical repeated configuration is idempotent
    }
    throw new HeliosConfigurationError(
      "Helios is already configured with different settings; " +
        "call Helios.shutdown() before reconfiguring",
    );
  }

  // Load optional instrumentations before touching any global state so a
  // missing peer dependency cannot leave a half-registered runtime behind.
  const instrumentations = await buildInstrumentations(config, extra);

  const diagnosticsInstalled = applyDiagnostics(config.diagnostics);

  const exporter = new OTLPTraceExporter({
    url: config.tracesEndpoint,
    headers: { Authorization: `Bearer ${config.apiKey}` },
    timeoutMillis: config.timeoutMillis,
  });
  const processor = new BatchSpanProcessor(exporter, {
    scheduledDelayMillis: config.batch.scheduledDelayMillis,
    maxQueueSize: config.batch.maxQueueSize,
    maxExportBatchSize: config.batch.maxExportBatchSize,
    exportTimeoutMillis: config.timeoutMillis,
  });
  const provider = new NodeTracerProvider({
    resource: buildResource(config),
    spanProcessors: [processor],
  });

  const registered = otelTrace.setGlobalTracerProvider(provider);
  if (!registered) {
    // A different global provider exists (not installed by this SDK, since
    // state is null). Refuse to replace it and leave global state untouched.
    await provider.shutdown().catch(() => undefined);
    if (diagnosticsInstalled) disableDiagnostics();
    throw new HeliosConfigurationError(
      "another global OpenTelemetry tracer provider is already registered; " +
        "Helios will not replace it. Shut down the existing provider first.",
    );
  }

  const contextManager = new AsyncLocalStorageContextManager();
  contextManager.enable();
  const ownsGlobalContextManager = context.setGlobalContextManager(contextManager);
  const ownsGlobalPropagator = propagation.setGlobalPropagator(
    new CompositePropagator({
      propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
    }),
  );

  let unregisterInstrumentations: (() => void) | null = null;
  if (instrumentations.length > 0) {
    const { registerInstrumentations } = await import("@opentelemetry/instrumentation");
    unregisterInstrumentations = registerInstrumentations({
      instrumentations,
      tracerProvider: provider,
    });
  }

  state = {
    snapshot,
    extraInstrumentations: extra,
    config,
    provider,
    tracer: provider.getTracer(TRACER_NAME, SDK_VERSION),
    contextManager,
    ownsGlobalContextManager,
    ownsGlobalPropagator,
    unregisterInstrumentations,
    diagnosticsInstalled,
    shutdownPromise: null,
  };
}

function reportExportFailure(operation: string, error: unknown): void {
  // Routine export failures must never crash the application; surface them
  // only through (redacted) diagnostics when enabled.
  const message = error instanceof Error ? error.message : String(error);
  diag.warn(`helios ${operation} failed: ${redactDiagnosticText(message)}`);
}

async function shutdown(): Promise<void> {
  const current = state;
  if (current === null) return; // idempotent
  if (current.shutdownPromise) return current.shutdownPromise;

  const run = (async () => {
    try {
      current.unregisterInstrumentations?.();
      try {
        await current.provider.shutdown();
      } catch (error) {
        reportExportFailure("shutdown flush", error);
      }
    } finally {
      otelTrace.disable();
      if (current.ownsGlobalContextManager) context.disable();
      if (current.ownsGlobalPropagator) propagation.disable();
      current.contextManager.disable();
      if (current.diagnosticsInstalled) disableDiagnostics();
      if (state === current) state = null;
    }
  })();
  current.shutdownPromise = run;
  return run;
}

function splitArgs<T>(
  optionsOrFn: HeliosSpanOptions | SpanCallback<T>,
  maybeFn?: SpanCallback<T>,
): [HeliosSpanOptions, SpanCallback<T>] {
  return typeof optionsOrFn === "function"
    ? [{}, optionsOrFn]
    : [optionsOrFn, maybeFn as SpanCallback<T>];
}

/**
 * Start a new **root** workflow trace (span type `agent` by default) and run
 * the callback inside it. Sync and async callbacks are supported; the return
 * value is preserved and errors are recorded, marked, and rethrown.
 */
function traceRoot<T>(name: string, fn: SpanCallback<T>): T;
function traceRoot<T>(name: string, options: HeliosSpanOptions, fn: SpanCallback<T>): T;
function traceRoot<T>(
  name: string,
  optionsOrFn: HeliosSpanOptions | SpanCallback<T>,
  maybeFn?: SpanCallback<T>,
): T {
  const [options, fn] = splitArgs(optionsOrFn, maybeFn);
  return runWithSpan(
    requireConfigured().tracer,
    name,
    { spanType: "agent", ...options, root: true },
    fn,
  );
}

/**
 * Start a span nested under the active context (or as a root when no span is
 * active) and run the callback inside it. Span type defaults to `custom`;
 * pass `spanType` for `llm`/`tool`/`retrieval`/`agent`.
 */
function childSpan<T>(name: string, fn: SpanCallback<T>): T;
function childSpan<T>(name: string, options: HeliosSpanOptions, fn: SpanCallback<T>): T;
function childSpan<T>(
  name: string,
  optionsOrFn: HeliosSpanOptions | SpanCallback<T>,
  maybeFn?: SpanCallback<T>,
): T {
  const [options, fn] = splitArgs(optionsOrFn, maybeFn);
  return runWithSpan(requireConfigured().tracer, name, options, fn);
}

/**
 * The Helios SDK entry point.
 *
 * ```ts
 * import { Helios } from "@helios-ai/sdk";
 *
 * await Helios.configure({
 *   apiKey: process.env.HELIOS_API_KEY!,
 *   endpoint: process.env.HELIOS_ENDPOINT!,
 *   serviceName: "support-agent",
 *   environment: "development",
 * });
 * ```
 */
export const Helios = {
  /** Configure the runtime. See {@link HeliosConfigureOptions}. */
  configure,

  /** True when a live (non-shut-down) runtime exists. */
  isConfigured(): boolean {
    return state !== null;
  },

  /** The Helios OpenTelemetry tracer for advanced/manual use. */
  getTracer(): Tracer {
    return requireConfigured().tracer;
  },

  trace: traceRoot,
  span: childSpan,

  /** The currently active OpenTelemetry span, if any. */
  getActiveSpan(): Span | undefined {
    return getActiveSpan();
  },

  /**
   * Flush all pending spans to Helios. Safe to call repeatedly. Routine
   * export failures are absorbed (reported via diagnostics when enabled)
   * rather than thrown into application code.
   */
  async forceFlush(): Promise<void> {
    if (state === null) return;
    try {
      await state.provider.forceFlush();
    } catch (error) {
      reportExportFailure("force flush", error);
    }
  },

  /**
   * Flush, stop exporting, unregister instrumentation, and release the
   * global OpenTelemetry registrations this SDK installed. Idempotent; after
   * shutdown, `configure()` may be called again.
   */
  shutdown,
} as const;

/** Test-only: drop runtime state without a clean shutdown. Not public API. */
export async function _resetForTests(): Promise<void> {
  try {
    await shutdown();
  } catch {
    state = null;
  }
  otelTrace.disable();
  context.disable();
  propagation.disable();
}
