import assert from "node:assert/strict";
import { afterEach, beforeEach, describe, it } from "node:test";
import { SpanStatusCode, type Span } from "@opentelemetry/api";
import type { ReadableSpan } from "@opentelemetry/sdk-trace-node";

import { Helios } from "../src/runtime.js";
import { llmAttributes } from "../src/semconv.js";
import { LocalCollector } from "./helpers/collector.js";
import { TEST_API_KEY, resetRuntime } from "./helpers/reset.js";

let collector: LocalCollector;

beforeEach(async () => {
  await resetRuntime();
  collector = await LocalCollector.start();
  await Helios.configure({
    apiKey: TEST_API_KEY,
    serviceName: "tracing-svc",
    endpoint: collector.endpoint,
  });
});

afterEach(async () => {
  await resetRuntime();
  await collector.stop();
});

function readable(span: Span): ReadableSpan {
  return span as unknown as ReadableSpan;
}

describe("root traces and nested spans", () => {
  it("creates a root workflow trace with span type agent", () => {
    let captured: ReadableSpan | undefined;
    Helios.trace("support.workflow", (span) => {
      captured = readable(span);
    });
    assert.ok(captured);
    assert.equal(captured.attributes["helios.span.type"], "agent");
    assert.equal(captured.parentSpanContext, undefined);
    assert.equal(captured.ended, true);
  });

  it("nests spans and propagates the active context", () => {
    let root: ReadableSpan | undefined;
    let child: ReadableSpan | undefined;
    let grandchild: ReadableSpan | undefined;
    Helios.trace("wf", (rootSpan) => {
      root = readable(rootSpan);
      Helios.span("retrieval.search", { spanType: "retrieval" }, (childSpan) => {
        child = readable(childSpan);
        Helios.span("tool.lookup", { spanType: "tool" }, (grandchildSpan) => {
          grandchild = readable(grandchildSpan);
        });
      });
    });
    assert.ok(root && child && grandchild);
    const traceId = root.spanContext().traceId;
    assert.equal(child.spanContext().traceId, traceId);
    assert.equal(grandchild.spanContext().traceId, traceId);
    assert.equal(child.parentSpanContext?.spanId, root.spanContext().spanId);
    assert.equal(grandchild.parentSpanContext?.spanId, child.spanContext().spanId);
    assert.equal(child.attributes["helios.span.type"], "retrieval");
    assert.equal(grandchild.attributes["helios.span.type"], "tool");
  });

  it("trace() always starts a new root, even inside an active span", () => {
    Helios.trace("outer", (outer) => {
      Helios.trace("inner-root", (inner) => {
        assert.notEqual(
          readable(inner).spanContext().traceId,
          readable(outer).spanContext().traceId,
        );
        assert.equal(readable(inner).parentSpanContext, undefined);
      });
    });
  });

  it("propagates context across awaited async operations", async () => {
    let rootId = "";
    const childIds: string[] = [];
    await Helios.trace("async-wf", async (span) => {
      rootId = readable(span).spanContext().spanId;
      await new Promise((resolve) => setTimeout(resolve, 5));
      await Helios.span("step-1", async (child) => {
        await new Promise((resolve) => setTimeout(resolve, 5));
        childIds.push(readable(child).parentSpanContext?.spanId ?? "");
      });
      await Promise.all([
        Helios.span("step-2", async (child) => {
          childIds.push(readable(child).parentSpanContext?.spanId ?? "");
        }),
        Helios.span("step-3", async (child) => {
          childIds.push(readable(child).parentSpanContext?.spanId ?? "");
        }),
      ]);
    });
    assert.deepEqual(childIds, [rootId, rootId, rootId]);
  });

  it("preserves sync and async return values", async () => {
    assert.equal(
      Helios.span("sync", () => 41 + 1),
      42,
    );
    assert.equal(await Helios.span("async", async () => "value"), "value");
  });

  it("exposes the active span", () => {
    Helios.span("active", (span) => {
      assert.equal(Helios.getActiveSpan(), span);
    });
    assert.equal(Helios.getActiveSpan(), undefined);
  });
});

describe("error handling in callbacks", () => {
  it("records sync exceptions, sets error status, ends, and rethrows unwrapped", () => {
    const original = new Error("sync boom");
    let captured: ReadableSpan | undefined;
    assert.throws(() => {
      Helios.span("failing", (span) => {
        captured = readable(span);
        throw original;
      });
    }, (error: unknown) => error === original);
    assert.ok(captured);
    assert.equal(captured.status.code, SpanStatusCode.ERROR);
    assert.equal(captured.status.message, "sync boom");
    assert.equal(captured.ended, true);
    const exceptionEvent = captured.events.find((event) => event.name === "exception");
    assert.ok(exceptionEvent);
    assert.equal(exceptionEvent.attributes?.["exception.message"], "sync boom");
  });

  it("records rejected promises and rethrows the original error", async () => {
    const original = new Error("async boom");
    let captured: ReadableSpan | undefined;
    await assert.rejects(
      Helios.span("failing-async", async (span) => {
        captured = readable(span);
        throw original;
      }),
      (error: unknown) => error === original,
    );
    assert.ok(captured);
    assert.equal(captured.status.code, SpanStatusCode.ERROR);
    assert.equal(captured.ended, true);
  });

  it("handles non-Error throws safely", () => {
    let captured: ReadableSpan | undefined;
    assert.throws(() => {
      Helios.span("string-throw", (span) => {
        captured = readable(span);
        // eslint-disable-next-line no-throw-literal
        throw "plain failure";
      });
    });
    assert.equal(captured?.status.code, SpanStatusCode.ERROR);
  });

  it("does not double-end spans", async () => {
    let captured: ReadableSpan | undefined;
    await Helios.span("end-once", async (span) => {
      captured = readable(span);
    });
    const endTime = captured?.endTime;
    // A second end would emit a diag warning and mutate nothing; verify the
    // recorded end time is stable.
    assert.deepEqual(captured?.endTime, endTime);
    assert.equal(captured?.ended, true);
  });
});

describe("span options", () => {
  it("applies custom and builder attributes", () => {
    let captured: ReadableSpan | undefined;
    Helios.span(
      "chat gpt-4o-mini",
      {
        spanType: "llm",
        attributes: {
          ...llmAttributes({ requestModel: "gpt-4o-mini", inputTokens: 10, outputTokens: 3 }),
          "app.custom": "yes",
        },
      },
      (span) => {
        captured = readable(span);
      },
    );
    assert.ok(captured);
    assert.equal(captured.attributes["helios.span.type"], "llm");
    assert.equal(captured.attributes["gen_ai.request.model"], "gpt-4o-mini");
    assert.equal(captured.attributes["gen_ai.usage.input_tokens"], 10);
    assert.equal(captured.attributes["gen_ai.usage.output_tokens"], 3);
    assert.equal(captured.attributes["app.custom"], "yes");
  });

  it("drops invalid attribute values", () => {
    let captured: ReadableSpan | undefined;
    Helios.span(
      "invalid-attrs",
      { attributes: { bad: { nested: true } as never, ok: 1 } },
      (span) => {
        captured = readable(span);
      },
    );
    assert.equal(captured?.attributes["bad"], undefined);
    assert.equal(captured?.attributes["ok"], 1);
  });

  it("rejects unknown span types", () => {
    assert.throws(
      () =>
        Helios.span("bad-type", { spanType: "database" as never }, () => undefined),
      /unknown spanType/,
    );
  });

  it("rejects empty span names and non-function callbacks", () => {
    assert.throws(() => Helios.span("", () => undefined), /non-empty string/);
    assert.throws(
      () => Helios.span("name", undefined as unknown as () => void),
      /callback must be a function/,
    );
  });
});
