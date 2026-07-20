import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  llmAttributes,
  normalizeAttributes,
  retrievalAttributes,
  toolAttributes,
  workflowAttributes,
} from "../src/semconv.js";

describe("llmAttributes", () => {
  it("maps every supported field to GenAI convention keys", () => {
    const attrs = llmAttributes({
      operation: "chat",
      requestModel: "gpt-4o-mini",
      responseModel: "gpt-4o-mini-2024",
      provider: "openai",
      inputTokens: 42,
      outputTokens: 7,
      finishReasons: ["stop"],
      responseId: "chatcmpl-123",
    });
    assert.deepEqual(attrs, {
      "gen_ai.operation.name": "chat",
      "gen_ai.request.model": "gpt-4o-mini",
      "gen_ai.response.model": "gpt-4o-mini-2024",
      "gen_ai.system": "openai",
      "gen_ai.usage.input_tokens": 42,
      "gen_ai.usage.output_tokens": 7,
      "gen_ai.response.finish_reasons": ["stop"],
      "gen_ai.response.id": "chatcmpl-123",
    });
  });

  it("requires numeric token counts and omits malformed values", () => {
    const attrs = llmAttributes({
      requestModel: "gpt-x",
      inputTokens: "100" as unknown as number,
      outputTokens: Number.NaN,
    });
    assert.equal(attrs["gen_ai.usage.input_tokens"], undefined);
    assert.equal(attrs["gen_ai.usage.output_tokens"], undefined);
    assert.equal(
      llmAttributes({ inputTokens: -5 })["gen_ai.usage.input_tokens"],
      undefined,
    );
    assert.equal(llmAttributes({ inputTokens: 10.9 })["gen_ai.usage.input_tokens"], 10);
    assert.equal(
      llmAttributes({ inputTokens: Infinity })["gen_ai.usage.input_tokens"],
      undefined,
    );
  });

  it("omits empty and undefined fields, never fabricating values", () => {
    assert.deepEqual(llmAttributes({}), {});
    assert.deepEqual(llmAttributes({ requestModel: "  " }), {});
  });

  it("never produces a cost attribute", () => {
    const attrs = llmAttributes({
      requestModel: "gpt-x",
      inputTokens: 1000,
      outputTokens: 1000,
    });
    assert.ok(!Object.keys(attrs).some((key) => key.toLowerCase().includes("cost")));
  });
});

describe("tool / retrieval / workflow attributes", () => {
  it("builds tool attributes", () => {
    assert.deepEqual(toolAttributes({ toolName: "kb.search", operation: "execute_tool" }), {
      "tool.name": "kb.search",
      "gen_ai.operation.name": "execute_tool",
    });
    assert.deepEqual(toolAttributes({}), {});
  });

  it("builds retrieval attributes with numeric document counts only", () => {
    assert.deepEqual(
      retrievalAttributes({ operation: "search", documentCount: 4, source: "vector-store" }),
      {
        "gen_ai.operation.name": "search",
        "retrieval.document_count": 4,
        "retrieval.source": "vector-store",
      },
    );
    assert.equal(
      retrievalAttributes({ documentCount: "four" as unknown as number })[
        "retrieval.document_count"
      ],
      undefined,
    );
  });

  it("builds workflow attributes", () => {
    assert.deepEqual(
      workflowAttributes({ agentName: "support-agent", stepName: "triage", runId: "run-7" }),
      {
        "gen_ai.agent.name": "support-agent",
        "helios.workflow.step": "triage",
        "helios.workflow.run_id": "run-7",
      },
    );
  });
});

describe("normalizeAttributes", () => {
  it("keeps valid scalars and homogeneous arrays", () => {
    assert.deepEqual(
      normalizeAttributes({
        s: "text",
        n: 3,
        b: true,
        arr: ["a", "b"],
        nums: [1, 2, 3],
      }),
      { s: "text", n: 3, b: true, arr: ["a", "b"], nums: [1, 2, 3] },
    );
  });

  it("drops invalid values instead of stringifying them", () => {
    const normalized = normalizeAttributes({
      obj: { secret: "payload" } as never,
      fn: (() => 1) as never,
      nan: Number.NaN,
      inf: Infinity,
      nil: null as never,
      undef: undefined,
      mixed: ["a", 1] as never,
      empty: [] as never,
    });
    assert.deepEqual(normalized, {});
  });

  it("bounds very long strings", () => {
    const value = "x".repeat(10_000);
    const normalized = normalizeAttributes({ long: value });
    assert.equal((normalized.long as string).length, 4096);
  });
});
