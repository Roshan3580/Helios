// Helios TypeScript SDK — official OpenAI auto-instrumentation example.
//
// CommonJS on purpose: the OpenTelemetry instrumentation patches `require`d
// modules (require-in-the-middle). STARTUP ORDER MATTERS — Helios.configure()
// must run BEFORE `openai` is required, which is why the require happens
// inside main() below. (Pure-ESM apps additionally need OpenTelemetry's ESM
// loader hooks, which this SDK does not configure; CommonJS is the tested path.)
//
// Required environment:
//   HELIOS_API_KEY    project API key with traces:ingest (hel_proj_…)
//   HELIOS_ENDPOINT   e.g. http://localhost:8000
//   OPENAI_API_KEY    your OpenAI key — used ONLY by the OpenAI client and
//                     kept completely separate from the Helios project key.
//
// This example performs a real OpenAI request when OPENAI_API_KEY is set.
// It is NOT run in CI and never runs automatically. Prompt/completion content
// is NOT captured by Helios (content capture is off by default); only model
// names, token counts, finish reasons, and response IDs reach Helios.
"use strict";

const { Helios } = require("@helios-ai/sdk");

async function main() {
  if (!process.env.OPENAI_API_KEY) {
    console.error(
      "OPENAI_API_KEY is not set. This example makes a real OpenAI request;\n" +
        "set your own key locally to run it (it is never required for CI/tests).",
    );
    process.exit(1);
  }

  // 1. Configure Helios FIRST (registers the official OpenAI instrumentation).
  await Helios.configure({
    apiKey: process.env.HELIOS_API_KEY,
    endpoint: process.env.HELIOS_ENDPOINT ?? "http://localhost:8000",
    serviceName: process.env.HELIOS_SERVICE_NAME ?? "ts-openai-example",
    environment: "development",
    instrumentations: { openai: true },
  });

  // 2. Require OpenAI AFTER configure() so the client is instrumented.
  const OpenAI = require("openai");
  const client = new OpenAI(); // reads OPENAI_API_KEY itself

  // 3. Wrap the call in a workflow trace; the instrumentation adds the
  //    `chat <model>` child span with model + token attributes automatically.
  await Helios.trace("openai.workflow", async () => {
    const completion = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: "Say hello in five words." }],
      max_tokens: 20,
    });
    console.log(`finish_reason: ${completion.choices[0]?.finish_reason}`);
  });

  await Helios.forceFlush();
  await Helios.shutdown();
  console.log("trace exported — the chat span carries tokens/model, not content");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
