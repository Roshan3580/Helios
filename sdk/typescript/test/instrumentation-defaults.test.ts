/**
 * Instrumentation is OFF by default. Runs in its own process so the `openai`
 * module is never patched here.
 */

import assert from "node:assert/strict";
import { get as httpGet } from "node:http";
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
  await Helios.configure({
    apiKey: TEST_API_KEY,
    serviceName: "defaults-svc",
    endpoint: collector.endpoint,
  });
});

after(async () => {
  await resetRuntime();
  await collector.stop();
  await fakeOpenAi.stop();
});

describe("instrumentation defaults", () => {
  it("openai instrumentation is disabled by default", async () => {
    const { default: OpenAI } = await import("openai");
    const client = new OpenAI({ apiKey: FAKE_OPENAI_KEY, baseURL: fakeOpenAi.baseUrl });
    const completion = await client.chat.completions.create({
      model: FAKE_MODEL,
      messages: [{ role: "user", content: FAKE_PROMPT }],
    });
    assert.equal(completion.choices[0]?.message.content, FAKE_COMPLETION);
    await Helios.forceFlush();
    assert.ok(!collector.bodiesInclude("gen_ai.operation.name"));
    assert.ok(!collector.bodiesInclude(FAKE_PROMPT));
  });

  it("node auto-instrumentation is disabled by default", async () => {
    await new Promise<void>((resolve, reject) => {
      httpGet(`${fakeOpenAi.baseUrl.replace(/\/v1$/, "")}/v1/ping`, (res) => {
        res.resume();
        res.on("end", resolve);
      }).on("error", reject);
    });
    await Helios.forceFlush();
    assert.ok(!collector.bodiesInclude("http.method"));
    assert.ok(!collector.bodiesInclude("http.request.method"));
  });
});
