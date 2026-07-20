/**
 * Minimal local OTLP collector for tests: records every request (method,
 * path, headers, raw body) and answers 200 (or a configured failure status).
 * Never contacts any external network.
 */

import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";

export interface CapturedRequest {
  method: string;
  url: string;
  headers: Record<string, string | string[] | undefined>;
  body: Buffer;
}

export class LocalCollector {
  private server: Server;
  readonly requests: CapturedRequest[] = [];
  /** Status code to answer with (set to 500 to simulate export failure). */
  responseStatus = 200;
  private port = 0;

  private constructor(server: Server) {
    this.server = server;
  }

  static async start(): Promise<LocalCollector> {
    const collector = new LocalCollector(
      createServer((req, res) => {
        const chunks: Buffer[] = [];
        req.on("data", (chunk: Buffer) => chunks.push(chunk));
        req.on("end", () => {
          collector.requests.push({
            method: req.method ?? "",
            url: req.url ?? "",
            headers: { ...req.headers },
            body: Buffer.concat(chunks),
          });
          res.statusCode = collector.responseStatus;
          res.setHeader("Content-Type", "application/x-protobuf");
          res.end();
        });
      }),
    );
    await new Promise<void>((resolve) =>
      collector.server.listen(0, "127.0.0.1", resolve),
    );
    collector.port = (collector.server.address() as AddressInfo).port;
    return collector;
  }

  get endpoint(): string {
    return `http://127.0.0.1:${this.port}`;
  }

  /** All request bodies concatenated, for substring presence checks. */
  allBodies(): Buffer {
    return Buffer.concat(this.requests.map((request) => request.body));
  }

  bodiesInclude(text: string): boolean {
    return this.allBodies().includes(Buffer.from(text, "utf8"));
  }

  async stop(): Promise<void> {
    await new Promise<void>((resolve) => this.server.close(() => resolve()));
  }
}
