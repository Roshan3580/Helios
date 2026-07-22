/**
 * Local fake OpenAI-compatible HTTP server. Answers POST /v1/chat/completions
 * with a deterministic completion payload. No external network is involved;
 * the "API key" used against it is a placeholder, never a real credential.
 */

import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

export const FAKE_PROMPT = "FAKE_PROMPT_DO_NOT_CAPTURE";
export const FAKE_COMPLETION = "FAKE_COMPLETION_DO_NOT_CAPTURE";
export const FAKE_OPENAI_KEY = "sk-test-fake-openai-key-not-real";
export const FAKE_MODEL = "gpt-4o-mini";
export const FAKE_RESPONSE_MODEL = "gpt-4o-mini-2024-fake";
export const FAKE_RESPONSE_ID = "chatcmpl-fake-123";

export class FakeOpenAiServer {
  private server: Server;
  readonly requests: Array<{ url: string; authorization?: string; body: string }> = [];
  private port = 0;

  private constructor(server: Server) {
    this.server = server;
  }

  static async start(): Promise<FakeOpenAiServer> {
    const fake = new FakeOpenAiServer(
      createServer((req, res) => {
        const chunks: Buffer[] = [];
        req.on("data", (chunk: Buffer) => chunks.push(chunk));
        req.on("end", () => {
          fake.requests.push({
            url: req.url ?? "",
            authorization: req.headers.authorization,
            body: Buffer.concat(chunks).toString("utf8"),
          });
          res.statusCode = 200;
          res.setHeader("Content-Type", "application/json");
          res.end(
            JSON.stringify({
              id: FAKE_RESPONSE_ID,
              object: "chat.completion",
              created: 1_700_000_000,
              model: FAKE_RESPONSE_MODEL,
              choices: [
                {
                  index: 0,
                  message: { role: "assistant", content: FAKE_COMPLETION },
                  finish_reason: "stop",
                },
              ],
              usage: { prompt_tokens: 21, completion_tokens: 8, total_tokens: 29 },
            }),
          );
        });
      }),
    );
    await new Promise<void>((resolve) => fake.server.listen(0, "127.0.0.1", resolve));
    fake.port = (fake.server.address() as AddressInfo).port;
    return fake;
  }

  get baseUrl(): string {
    return `http://127.0.0.1:${this.port}/v1`;
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }
}
