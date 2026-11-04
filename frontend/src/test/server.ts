import { vi } from "vitest";
import { catalog, farm, health, user } from "./fixtures";

/** A response with an explicit status. Plain values in the route table are sent as 200 JSON. */
export class Reply {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body?: unknown) {
    this.status = status;
    this.body = body;
  }
}

export const fail = (status: number, code: string, message: string) =>
  new Reply(status, { error: { code, message, request_id: "req-test" } });

export interface Call {
  method: string;
  path: string;
  query: URLSearchParams;
  body: unknown;
  token: string | null;
}

type Handler = unknown | ((call: Call) => unknown);

const DEFAULTS: Record<string, Handler> = {
  "POST /api/session/guest": { token: "new-token", user },
  "GET /api/session/me": user,
  "GET /api/health": health,
  "GET /api/crops": catalog,
  "GET /api/farms": [farm],
  "GET /api/conversations": [],
  "GET /api/recommendations": [],
};

function toResponse(result: unknown): Response {
  if (result instanceof Response) return result;
  const reply = result instanceof Reply ? result : new Reply(200, result);
  if (reply.status === 204 || reply.body === undefined) return new Response(null, { status: 204 });
  return new Response(JSON.stringify(reply.body), {
    status: reply.status,
    headers: { "Content-Type": "application/json" },
  });
}

/**
 * Replaces fetch with a route table keyed "METHOD /path", so no test can reach a live API. A route
 * nobody declared is recorded in `unhandled` and answered with a 500, which fails loudly on screen.
 */
export function mockServer(routes: Record<string, Handler> = {}) {
  const table = { ...DEFAULTS, ...routes };
  const calls: Call[] = [];
  const unhandled: string[] = [];

  vi.stubGlobal("fetch", async (input: string, init: RequestInit = {}) => {
    const url = new URL(input, "http://farmagent.test");
    const method = init.method ?? "GET";
    const headers = new Headers(init.headers);
    const call: Call = {
      method,
      path: url.pathname,
      query: url.searchParams,
      body: typeof init.body === "string" ? JSON.parse(init.body) : undefined,
      token: headers.get("X-Guest-Token"),
    };
    calls.push(call);
    const key = `${method} ${url.pathname}`;
    if (!(key in table)) {
      unhandled.push(key);
      return toResponse(fail(500, "unmocked_route", `No test route for ${key}`));
    }
    const route = table[key];
    return toResponse(typeof route === "function" ? await route(call) : route);
  });

  return {
    calls,
    unhandled,
    to: (method: string, path: string) => calls.filter((call) => call.method === method && call.path === path),
  };
}

/** A request that never answers, for looking at a loading state. */
export const pending = () => new Promise(() => {});

/** An answer the test releases by hand, for looking at what is on screen before it arrives. */
export function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

/** A server-sent event stream the test feeds one frame at a time. */
export function eventStream() {
  const encoder = new TextEncoder();
  let controller!: ReadableStreamDefaultController<Uint8Array>;
  const stream = new ReadableStream<Uint8Array>({
    start(value) {
      controller = value;
    },
  });
  return {
    response: new Response(stream, { headers: { "Content-Type": "text/event-stream" } }),
    push: (frame: unknown) => controller.enqueue(encoder.encode(`data: ${JSON.stringify(frame)}\n\n`)),
    close: () => controller.close(),
  };
}
