// TypeScript consumer compilation + execution smoke for the packed artifact.
// Verifies declaration files resolve under NodeNext and the typed API works.
import assert from "node:assert/strict";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";

import {
  Helios,
  llmAttributes,
  retrievalAttributes,
  type HeliosConfigureOptions,
  type Span,
} from "@helios-ai/sdk";

const KEY = "hel_proj_0123456789abcdef_fixturesecretfixturesecret";

async function main(): Promise<void> {
  const requests: Buffer[] = [];
  const server = createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (chunk: Buffer) => chunks.push(chunk));
    req.on("end", () => {
      requests.push(Buffer.concat(chunks));
      res.statusCode = 200;
      res.end();
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;

  const options: HeliosConfigureOptions = {
    apiKey: KEY,
    serviceName: "ts-consumer",
    endpoint: `http://127.0.0.1:${port}`,
  };
  await Helios.configure(options);

  const value: number = await Helios.trace("ts.workflow", async (span: Span) => {
    span.setAttribute("app.step", "root");
    Helios.span(
      "retrieval.search",
      { spanType: "retrieval", attributes: retrievalAttributes({ documentCount: 2 }) },
      () => undefined,
    );
    return 7;
  });
  assert.equal(value, 7);
  assert.deepEqual(llmAttributes({ inputTokens: Number.NaN }), {});

  await Helios.shutdown();
  server.close();
  assert.equal(requests.length, 1);
  assert.ok(requests[0]!.includes(Buffer.from("ts.workflow")));
  console.log("TypeScript consumer smoke: OK");
}

void main();
