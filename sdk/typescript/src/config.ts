/**
 * Configuration resolution for the Helios Node SDK.
 *
 * Resolves explicit options and environment variables into a validated,
 * frozen config. No OpenTelemetry imports, no network activity, no logging.
 *
 * Precedence: explicit option > Helios env var > recognized OTel env var >
 * default (identical to the Python SDK).
 *
 * Environment variables:
 *   HELIOS_API_KEY          required (no default)
 *   HELIOS_ENDPOINT         base URL or full ingest URL, default http://localhost:8000
 *   HELIOS_SERVICE_NAME     required unless OTEL_SERVICE_NAME is set
 *   HELIOS_SERVICE_VERSION  optional service version
 *   HELIOS_ENVIRONMENT      optional deployment environment
 *   HELIOS_CAPTURE_CONTENT  optional bool, default false
 */

import type { Attributes } from "@opentelemetry/api";
import { HeliosConfigurationError } from "./errors.js";
import { normalizeAttributes } from "./semconv.js";

export const DEFAULT_ENDPOINT = "http://localhost:8000";
export const TRACES_PATH = "/v1/otlp/traces";
export const DEFAULT_TIMEOUT_MILLIS = 10_000;
const MIN_TIMEOUT_MILLIS = 100;
const MAX_TIMEOUT_MILLIS = 120_000;

const MAX_RESOURCE_ATTRIBUTES = 32;
const MAX_RESOURCE_STRING_LENGTH = 256;

// Keys the SDK owns; user resource attributes may not override them.
const PROTECTED_RESOURCE_KEYS = new Set([
  "service.name",
  "service.version",
  "deployment.environment.name",
]);
const PROTECTED_RESOURCE_PREFIXES = ["telemetry.sdk.", "helios.sdk."];
const SECRET_LIKE_KEY_FRAGMENTS = [
  "authorization",
  "api_key",
  "api-key",
  "apikey",
  "password",
  "passwd",
  "secret",
  "token",
  "cookie",
  "session",
  "credential",
];

// hel_proj_<lookup>_<secret>; validated structurally without ever echoing it.
const API_KEY_PATTERN = /^hel_proj_[A-Za-z0-9]+_[A-Za-z0-9_-]+$/;

export type DiagnosticsLevel = "none" | "error" | "warn" | "info" | "debug";

export interface HeliosBatchOptions {
  /** Delay between batch exports in ms (10–60000). */
  scheduledDelayMillis?: number;
  /** Maximum queued spans before drop (1–8192). */
  maxQueueSize?: number;
  /** Maximum spans per export batch (1–2048, ≤ maxQueueSize). */
  maxExportBatchSize?: number;
}

export interface HeliosInstrumentationOptions {
  /**
   * Enable the official `@opentelemetry/auto-instrumentations-node` bundle
   * (optional peer dependency). Disabled by default. Pass an object to turn
   * off known-noisy instrumentations by package name.
   */
  node?: boolean | { disabledInstrumentations?: string[] };
  /**
   * Enable the official `@opentelemetry/instrumentation-openai` package
   * (optional peer dependency). Disabled by default. Prompt/completion
   * content is never captured unless `captureContent` is explicitly true.
   */
  openai?: boolean;
}

export interface HeliosConfigureOptions {
  /** Helios project API key (`hel_proj_…`). Required. Never logged. */
  apiKey?: string;
  /** Helios base URL or full `/v1/otlp/traces` URL. */
  endpoint?: string;
  /** OTel `service.name`. Required (or HELIOS_SERVICE_NAME / OTEL_SERVICE_NAME). */
  serviceName?: string;
  /** Optional OTel `service.version`. */
  serviceVersion?: string;
  /** Optional deployment environment → `deployment.environment.name`. */
  environment?: string;
  /** Exporter timeout in milliseconds (100–120000, default 10000). */
  timeoutMillis?: number;
  /** Batch span processor tuning within safe bounds. */
  batch?: HeliosBatchOptions;
  /** Extra OTel resource attributes (validated, bounded, non-secret). */
  resourceAttributes?: Attributes;
  /** Optional auto-instrumentation toggles. All disabled by default. */
  instrumentations?: HeliosInstrumentationOptions;
  /**
   * Additional caller-constructed OpenTelemetry instrumentations to register
   * (must implement the `Instrumentation` interface).
   */
  extraInstrumentations?: unknown[];
  /**
   * Opt in to GenAI prompt/completion content capture for the OpenAI
   * instrumentation. Default false: Helios never captures content unless
   * this is explicitly enabled.
   */
  captureContent?: boolean;
  /**
   * Permit plain HTTP for a non-loopback endpoint (development only).
   * Loopback HTTP (localhost / 127.0.0.1 / ::1) is always allowed.
   */
  allowInsecureHttp?: boolean;
  /** Development diagnostics level. Default "none". Output is redacted. */
  diagnostics?: DiagnosticsLevel;
}

export interface ResolvedHeliosConfig {
  readonly apiKey: string;
  readonly endpoint: string;
  readonly tracesEndpoint: string;
  readonly serviceName: string;
  readonly serviceVersion?: string;
  readonly environment?: string;
  readonly timeoutMillis: number;
  readonly batch: Required<HeliosBatchOptions>;
  readonly resourceAttributes: Attributes;
  readonly instrumentations: { node: boolean | { disabledInstrumentations: string[] }; openai: boolean };
  readonly extraInstrumentations: unknown[];
  readonly captureContent: boolean;
  readonly diagnostics: DiagnosticsLevel;
}

type EnvSource = Record<string, string | undefined>;

const TRUE_VALUES = new Set(["true", "1", "yes", "on"]);
const FALSE_VALUES = new Set(["false", "0", "no", "off", ""]);

function parseBool(value: unknown, fieldName: string): boolean {
  if (typeof value === "boolean") return value;
  if (value === undefined || value === null) return false;
  const text = String(value).trim().toLowerCase();
  if (TRUE_VALUES.has(text)) return true;
  if (FALSE_VALUES.has(text)) return false;
  throw new HeliosConfigurationError(
    `invalid boolean for ${fieldName} (use true/false)`,
  );
}

function firstNonEmpty(...values: Array<string | undefined>): string | undefined {
  for (const value of values) {
    if (value !== undefined && value !== "") return value;
  }
  return undefined;
}

const LOOPBACK_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]", "::1", "0.0.0.0"]);

function isLoopbackHostname(hostname: string): boolean {
  const lowered = hostname.toLowerCase();
  if (LOOPBACK_HOSTNAMES.has(lowered)) return true;
  if (lowered.endsWith(".localhost")) return true;
  // 127.0.0.0/8
  if (/^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(lowered)) return true;
  return false;
}

/**
 * Normalize a Helios endpoint into (base URL, full OTLP traces URL).
 *
 * Accepts either the base URL or the full ingest URL; strips trailing
 * slashes; never double-appends the traces path. Only http/https protocols
 * are accepted, and http requires a loopback host unless `allowInsecureHttp`.
 */
export function normalizeEndpoint(
  raw: string,
  options: { allowInsecureHttp?: boolean } = {},
): { endpoint: string; tracesEndpoint: string } {
  const trimmedInput = raw.trim();
  let url: URL;
  try {
    url = new URL(trimmedInput);
  } catch {
    throw new HeliosConfigurationError(
      `endpoint is not a valid URL: ${JSON.stringify(trimmedInput)}`,
    );
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") {
    throw new HeliosConfigurationError(
      `endpoint protocol must be http or https (got ${url.protocol.replace(/:$/, "")})`,
    );
  }
  if (url.username || url.password) {
    throw new HeliosConfigurationError(
      "endpoint must not contain credentials; authentication uses the Authorization header",
    );
  }
  if (url.search || url.hash) {
    throw new HeliosConfigurationError(
      "endpoint must not contain query parameters or fragments",
    );
  }
  if (
    url.protocol === "http:" &&
    !isLoopbackHostname(url.hostname) &&
    !options.allowInsecureHttp
  ) {
    throw new HeliosConfigurationError(
      `plain HTTP is only allowed for loopback endpoints; use https for ${url.hostname} ` +
        "or set allowInsecureHttp: true for development",
    );
  }

  const withoutTrailing = `${url.origin}${url.pathname}`.replace(/\/+$/, "");
  if (withoutTrailing.endsWith(TRACES_PATH)) {
    return {
      endpoint: withoutTrailing.slice(0, -TRACES_PATH.length) || withoutTrailing,
      tracesEndpoint: withoutTrailing,
    };
  }
  return {
    endpoint: withoutTrailing,
    tracesEndpoint: `${withoutTrailing}${TRACES_PATH}`,
  };
}

function validateApiKey(raw: string | undefined): string {
  if (raw === undefined || String(raw).trim().length === 0) {
    throw new HeliosConfigurationError(
      "apiKey is required (pass apiKey or set HELIOS_API_KEY)",
    );
  }
  const key = String(raw).trim();
  if (!API_KEY_PATTERN.test(key)) {
    // Never echo the provided value.
    throw new HeliosConfigurationError(
      "apiKey does not look like a Helios project API key " +
        "(expected the hel_proj_ prefix); the provided value was not logged",
    );
  }
  return key;
}

function validateResourceAttributes(attributes: Attributes | undefined): Attributes {
  if (!attributes) return {};
  const normalized = normalizeAttributes(attributes);
  const out: Attributes = {};
  let count = 0;
  for (const [key, value] of Object.entries(normalized)) {
    const lowered = key.toLowerCase();
    if (PROTECTED_RESOURCE_KEYS.has(key)) {
      throw new HeliosConfigurationError(
        `resource attribute ${JSON.stringify(key)} is managed by the SDK; ` +
          "use the dedicated configuration option instead",
      );
    }
    if (PROTECTED_RESOURCE_PREFIXES.some((prefix) => lowered.startsWith(prefix))) {
      throw new HeliosConfigurationError(
        `resource attribute ${JSON.stringify(key)} uses a reserved prefix`,
      );
    }
    if (SECRET_LIKE_KEY_FRAGMENTS.some((fragment) => lowered.includes(fragment))) {
      // Silently dropping a secret could hide a bug; reject loudly (value not echoed).
      throw new HeliosConfigurationError(
        `resource attribute ${JSON.stringify(key)} looks secret-like and was rejected`,
      );
    }
    if (count >= MAX_RESOURCE_ATTRIBUTES) {
      throw new HeliosConfigurationError(
        `too many resource attributes (max ${MAX_RESOURCE_ATTRIBUTES})`,
      );
    }
    if (typeof value === "string" && value.length > MAX_RESOURCE_STRING_LENGTH) {
      out[key] = value.slice(0, MAX_RESOURCE_STRING_LENGTH);
    } else {
      out[key] = value;
    }
    count += 1;
  }
  return out;
}

function validateIntInRange(
  value: number | undefined,
  fallback: number,
  min: number,
  max: number,
  fieldName: string,
): number {
  if (value === undefined) return fallback;
  if (typeof value !== "number" || !Number.isFinite(value) || !Number.isInteger(value)) {
    throw new HeliosConfigurationError(`${fieldName} must be an integer`);
  }
  if (value < min || value > max) {
    throw new HeliosConfigurationError(
      `${fieldName} must be between ${min} and ${max} (got ${value})`,
    );
  }
  return value;
}

const DIAGNOSTIC_LEVELS: DiagnosticsLevel[] = ["none", "error", "warn", "info", "debug"];

/** Build a validated, frozen config from explicit options plus environment. */
export function resolveConfig(
  options: HeliosConfigureOptions = {},
  env: EnvSource = process.env,
): ResolvedHeliosConfig {
  const apiKey = validateApiKey(firstNonEmpty(options.apiKey, env["HELIOS_API_KEY"]));

  const serviceName = firstNonEmpty(
    options.serviceName,
    env["HELIOS_SERVICE_NAME"],
    env["OTEL_SERVICE_NAME"],
  )?.trim();
  if (!serviceName) {
    throw new HeliosConfigurationError(
      "serviceName is required (pass serviceName or set HELIOS_SERVICE_NAME / OTEL_SERVICE_NAME)",
    );
  }

  const rawEndpoint =
    firstNonEmpty(options.endpoint, env["HELIOS_ENDPOINT"]) ?? DEFAULT_ENDPOINT;
  const { endpoint, tracesEndpoint } = normalizeEndpoint(rawEndpoint, {
    allowInsecureHttp: options.allowInsecureHttp === true,
  });

  const serviceVersion =
    firstNonEmpty(options.serviceVersion, env["HELIOS_SERVICE_VERSION"])?.trim() ||
    undefined;
  const environment =
    firstNonEmpty(options.environment, env["HELIOS_ENVIRONMENT"])?.trim() || undefined;

  const timeoutMillis = validateIntInRange(
    options.timeoutMillis,
    DEFAULT_TIMEOUT_MILLIS,
    MIN_TIMEOUT_MILLIS,
    MAX_TIMEOUT_MILLIS,
    "timeoutMillis",
  );

  const maxQueueSize = validateIntInRange(
    options.batch?.maxQueueSize,
    2048,
    1,
    8192,
    "batch.maxQueueSize",
  );
  const maxExportBatchSize = validateIntInRange(
    options.batch?.maxExportBatchSize,
    512,
    1,
    2048,
    "batch.maxExportBatchSize",
  );
  if (maxExportBatchSize > maxQueueSize) {
    throw new HeliosConfigurationError(
      "batch.maxExportBatchSize must not exceed batch.maxQueueSize",
    );
  }
  const scheduledDelayMillis = validateIntInRange(
    options.batch?.scheduledDelayMillis,
    2000,
    10,
    60_000,
    "batch.scheduledDelayMillis",
  );

  const captureContent =
    options.captureContent === undefined
      ? parseBool(env["HELIOS_CAPTURE_CONTENT"], "HELIOS_CAPTURE_CONTENT")
      : parseBool(options.captureContent, "captureContent");

  const diagnostics = options.diagnostics ?? "none";
  if (!DIAGNOSTIC_LEVELS.includes(diagnostics)) {
    throw new HeliosConfigurationError(
      `diagnostics must be one of ${DIAGNOSTIC_LEVELS.join(", ")}`,
    );
  }

  const nodeOption = options.instrumentations?.node ?? false;
  let node: boolean | { disabledInstrumentations: string[] };
  if (typeof nodeOption === "boolean") {
    node = nodeOption;
  } else if (nodeOption && typeof nodeOption === "object") {
    const disabled = nodeOption.disabledInstrumentations ?? [];
    if (!Array.isArray(disabled) || !disabled.every((name) => typeof name === "string")) {
      throw new HeliosConfigurationError(
        "instrumentations.node.disabledInstrumentations must be a string array",
      );
    }
    node = { disabledInstrumentations: [...disabled].sort() };
  } else {
    throw new HeliosConfigurationError("instrumentations.node must be a boolean or object");
  }

  const openai = parseBool(options.instrumentations?.openai ?? false, "instrumentations.openai");

  const extraInstrumentations = options.extraInstrumentations ?? [];
  if (!Array.isArray(extraInstrumentations)) {
    throw new HeliosConfigurationError("extraInstrumentations must be an array");
  }

  return Object.freeze({
    apiKey,
    endpoint,
    tracesEndpoint,
    serviceName,
    serviceVersion,
    environment,
    timeoutMillis,
    batch: Object.freeze({ scheduledDelayMillis, maxQueueSize, maxExportBatchSize }),
    resourceAttributes: Object.freeze(
      validateResourceAttributes(options.resourceAttributes),
    ),
    instrumentations: Object.freeze({ node, openai }),
    extraInstrumentations: Object.freeze([...extraInstrumentations]) as unknown[],
    captureContent,
    diagnostics,
  });
}

/**
 * Stable snapshot for idempotence comparison. Includes the API key value (so
 * a different key is a conflicting configuration) but is never logged; extra
 * instrumentations are compared by identity in the runtime, not here.
 */
export function configSnapshot(config: ResolvedHeliosConfig): string {
  return JSON.stringify({
    apiKey: config.apiKey,
    endpoint: config.endpoint,
    tracesEndpoint: config.tracesEndpoint,
    serviceName: config.serviceName,
    serviceVersion: config.serviceVersion ?? null,
    environment: config.environment ?? null,
    timeoutMillis: config.timeoutMillis,
    batch: config.batch,
    resourceAttributes: Object.fromEntries(
      Object.entries(config.resourceAttributes).sort(([a], [b]) => a.localeCompare(b)),
    ),
    instrumentations: config.instrumentations,
    captureContent: config.captureContent,
    diagnostics: config.diagnostics,
  });
}
