/**
 * Helios owns the content-privacy default: even when the upstream
 * OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT env var is set to true,
 * prompt/completion content is NOT captured unless Helios `captureContent`
 * is explicitly enabled. Own process so the openai module patches freshly.
 */

import assert from "node:assert/strict";
import { after, before, describe, it } from "node:test";

import { Helios } from "../src/runtime.js";
import { LocalCollector } from "./helpers/collector.js";
import {
  FAKE_COMPLETION,
  FAKE_MODEL,
  FAKE_OPENAI_KEY,
  FAKE_PROMPT,
  FakeOpenAiServer,
} from "./helpers/fake-openai.js";
import { TEST_API_KEY, resetRuntime } from "./helpers/reset.js";

let collector: LocalCollector;
let fakeOpenAi: FakeOpenAiServer;

before(async () => {
  await resetRuntime();
  collector = await LocalCollector.start();
  fakeOpenAi = await FakeOpenAiServer.start();
  process.env["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "true";
  await Helios.configure({
    apiKey: TEST_API_KEY,
    serviceName: "override-svc",
    endpoint: collector.endpoint,
    instrumentations: { openai: true },
  });
});

after(async () => {
  await resetRuntime();
  await collector.stop();
  await fakeOpenAi.stop();
});

describe("content capture stays off despite upstream env override", () => {
  it("emits token attributes but no prompt/completion content", async () => {
    const { default: OpenAI } = await import("openai");
    const client = new OpenAI({ apiKey: FAKE_OPENAI_KEY, baseURL: fakeOpenAi.baseUrl });
    await client.chat.completions.create({
      model: FAKE_MODEL,
      messages: [{ role: "user", content: FAKE_PROMPT }],
    });
    await Helios.forceFlush();
    const body = collector.allBodies();
    assert.ok(body.includes(Buffer.from("gen_ai.usage.input_tokens")));
    assert.ok(!body.includes(Buffer.from(FAKE_PROMPT)));
    assert.ok(!body.includes(Buffer.from(FAKE_COMPLETION)));
  });
});
