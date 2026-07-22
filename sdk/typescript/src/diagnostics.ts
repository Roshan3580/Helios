/**
 * Optional, redacted development diagnostics.
 *
 * Default is silence. When enabled, messages route to the OpenTelemetry diag
 * API through a redacting console logger: project API keys, bearer values,
 * and provider-key-shaped strings are masked before anything is written.
 * Exporter payloads and prompt/completion content are never logged by the
 * SDK itself.
 */

import { diag, DiagLogLevel, type DiagLogger } from "@opentelemetry/api";
import type { DiagnosticsLevel } from "./config.js";

const REDACTIONS: Array<[RegExp, string]> = [
  [/hel_proj_[A-Za-z0-9_-]+/g, "hel_proj_[REDACTED]"],
  [/\bBearer\s+[^\s"',;]+/gi, "Bearer [REDACTED]"],
  [/\bsk-[A-Za-z0-9_-]{8,}\b/g, "sk-[REDACTED]"],
  [/\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/g, "[REDACTED_JWT]"],
];

/** Redact secret-shaped substrings from one diagnostic argument. */
export function redactDiagnosticText(text: string): string {
  let out = text;
  for (const [pattern, replacement] of REDACTIONS) {
    out = out.replace(pattern, replacement);
  }
  return out;
}

function redactArg(arg: unknown): unknown {
  if (typeof arg === "string") return redactDiagnosticText(arg);
  if (arg instanceof Error) {
    return redactDiagnosticText(`${arg.name}: ${arg.message}`);
  }
  if (typeof arg === "object" && arg !== null) {
    try {
      return redactDiagnosticText(JSON.stringify(arg));
    } catch {
      return "[unserializable]";
    }
  }
  return arg;
}

type ConsoleLike = Pick<Console, "error" | "warn" | "info" | "debug">;

/** Console-backed OTel diag logger that redacts secrets in every argument. */
export function createRedactingDiagLogger(target: ConsoleLike = console): DiagLogger {
  const emit =
    (method: keyof ConsoleLike) =>
    (message: string, ...args: unknown[]) => {
      target[method]("[helios-sdk]", redactArg(message), ...args.map(redactArg));
    };
  return {
    error: emit("error"),
    warn: emit("warn"),
    info: emit("info"),
    debug: emit("debug"),
    verbose: emit("debug"),
  };
}

const LEVEL_MAP: Record<Exclude<DiagnosticsLevel, "none">, DiagLogLevel> = {
  error: DiagLogLevel.ERROR,
  warn: DiagLogLevel.WARN,
  info: DiagLogLevel.INFO,
  debug: DiagLogLevel.DEBUG,
};

/** Install (or leave silent) the redacted diag logger. Returns true if set. */
export function applyDiagnostics(level: DiagnosticsLevel, target?: ConsoleLike): boolean {
  if (level === "none") return false;
  diag.setLogger(createRedactingDiagLogger(target), {
    logLevel: LEVEL_MAP[level],
    suppressOverrideMessage: true,
  });
  return true;
}

/** Remove any diag logger the SDK installed. */
export function disableDiagnostics(): void {
  diag.disable();
}
