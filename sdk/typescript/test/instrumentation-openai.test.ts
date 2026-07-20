/**
 * Official OpenAI instrumentation against a local fake OpenAI server.
 *
 * Runs as compiled CommonJS so require-in-the-middle patching applies. The
 * `openai` module is imported only AFTER Helios.configure() registered the
 * instrumentation (the documented startup ordering); no external network
 * request occurs.
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
  FAKE_RESPONSE_ID,
  FAKE_RESPONSE_MODEL,
  FakeOpenAiServer,
} from "./helpers/fake-openai.js";
import { TEST_API_KEY, resetRuntime } from "./helpers/reset.js";

let collector: LocalCollector;
let fakeOpenAi: FakeOpenAiServer;

before(async () => {
  await resetRuntime();
  collector = await LocalCollector.start();
  fakeOpenAi = await FakeOpenAiServer.start();
  await Helios.configure({
    apiKey: TEST_API_KEY,
    serviceName: "openai-svc",
    endpoint: collector.endpoint,
    instrumentations: { openai: true },
  });
  // Identical repeated configuration is idempotent and must not re-register
  // (a duplicate registration would double-patch and duplicate spans below).
  await Helios.configure({
    apiKey: TEST_API_KEY,
    serviceName: "openai-svc",
    endpoint: collector.endpoint,
    instrumentations: { openai: true },
  });
});

after(async () => {
  await resetRuntime();
  await collector.stop();
  await fakeOpenAi.stop();
});

async function callFakeOpenAi(): Promise<void> {
  const { default: OpenAI } = await import("openai");
  const client = new OpenAI({ apiKey: FAKE_OPENAI_KEY, baseURL: fakeOpenAi.baseUrl });
  const completion = await client.chat.completions.create({
    model: FAKE_MODEL,
    messages: [{ role: "user", content: FAKE_PROMPT }],
  });
  assert.equal(completion.choices[0]?.message.content, FAKE_COMPLETION);
}

describe("OpenAI instrumentation (enabled)", () => {
  it("creates spans with model and token attributes, no content, no secrets", async () => {
    await callFakeOpenAi();
    await Helios.forceFlush();

    const body = collector.allBodies();
    assert.ok(body.length > 0, "expected exported spans");
    assert.ok(body.includes(Buffer.from(`chat ${FAKE_MODEL}`)), "expected a chat span");
    assert.ok(body.includes(Buffer.from(FAKE_RESPONSE_MODEL)));
    assert.ok(body.includes(Buffer.from("gen_ai.usage.input_tokens")));
    assert.ok(body.includes(Buffer.from("gen_ai.usage.output_tokens")));
    assert.ok(body.includes(Buffer.from(FAKE_RESPONSE_ID)));
    // Content privacy: prompt/completion text never leaves the process.
    assert.ok(!body.includes(Buffer.from(FAKE_PROMPT)));
    assert.ok(!body.includes(Buffer.from(FAKE_COMPLETION)));
    // No OpenAI or Helios credentials in the payload.
    assert.ok(!body.includes(Buffer.from(FAKE_OPENAI_KEY)));
    assert.ok(!body.includes(Buffer.from(TEST_API_KEY)));
    // The fake server received the request; nothing went anywhere else.
    assert.equal(fakeOpenAi.requests.length, 1);
    assert.equal(fakeOpenAi.requests[0]?.authorization, `Bearer ${FAKE_OPENAI_KEY}`);
  });

  it("one call produces exactly one chat span (no duplicate patching)", async () => {
    const before = collector
      .allBodies()
      .toString("latin1")
      .split(`chat ${FAKE_MODEL}`).length;
    await callFakeOpenAi();
    await Helios.forceFlush();
    const afterCount = collector
      .allBodies()
      .toString("latin1")
      .split(`chat ${FAKE_MODEL}`).length;
    assert.equal(afterCount - before, 1);
  });
});
