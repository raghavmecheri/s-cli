/**
 * CDP connection management — stub.
 *
 * TODO: Implement CDP WebSocket connection matching python/scli/core.py:
 * - Connect to ws://127.0.0.1:9222/devtools/page/{id}
 * - Send Runtime.evaluate messages
 * - Parse responses
 *
 * Reference: python/scli/core.py _cdp_eval()
 */

import WebSocket from "ws";

export class CDPConnection {
  private ws: WebSocket | null = null;
  private msgId = 0;

  constructor(private wsUrl: string) {}

  async connect(): Promise<void> {
    // TODO: Implement WebSocket connection
    throw new Error("Not implemented — see python/scli/core.py for reference");
  }

  async evaluate(expression: string, awaitPromise = true): Promise<unknown> {
    // TODO: Send Runtime.evaluate, wait for matching response ID
    throw new Error("Not implemented — see python/scli/core.py _cdp_eval()");
  }

  close(): void {
    this.ws?.close();
  }
}
