// Helios TypeScript SDK — basic Node quickstart (plain JavaScript, ESM).
//
// Emits one root workflow trace with nested retrieval / LLM / tool spans to
// your Helios backend, then flushes and shuts down cleanly.
//
// Required environment:
//   HELIOS_API_KEY       project API key with traces:ingest (hel_proj_…)
//   HELIOS_ENDPOINT      e.g. http://localhost:8000
//   HELIOS_SERVICE_NAME  optional (defaults below)
import {
  Helios,
  llmAttributes,
  retrievalAttributes,
  toolAttributes,
} from "@helios-ai/sdk";

await Helios.configure({
  apiKey: process.env.HELIOS_API_KEY, // never hardcode the key
  endpoint: process.env.HELIOS_ENDPOINT ?? "http://localhost:8000",
  serviceName: process.env.HELIOS_SERVICE_NAME ?? "ts-basic-example",
  environment: "development",
});

const answer = await Helios.trace("support.workflow", async () => {
  const documents = await Helios.span(
    "retrieval.search",
    { spanType: "retrieval", attributes: retrievalAttributes({ operation: "search", documentCount: 3 }) },
    async () => ["policy.md", "faq.md", "pricing.md"],
  );

  await Helios.span(
    "tool.lookup_policy",
    { spanType: "tool", attributes: toolAttributes({ toolName: "lookup_policy" }) },
    async () => undefined,
  );

  // A model span with explicit (deterministic) metadata — no provider call.
  return Helios.span(
    "chat gpt-4o-mini",
    {
      spanType: "llm",
      attributes: llmAttributes({
        operation: "chat",
        requestModel: "gpt-4o-mini",
        provider: "openai",
        inputTokens: 42,
        outputTokens: 12,
      }),
    },
    async () => `answered using ${documents.length} documents`,
  );
});

console.log(`workflow result: ${answer}`);

await Helios.forceFlush();
await Helios.shutdown();
console.log("trace exported — open the Helios console to inspect it");
