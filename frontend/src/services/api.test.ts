import { describe, expect, it, vi } from "vitest";
import { api, ApiError, createSseParser, streamChat, tokenStore } from "./api";
import { chatResponse } from "@/test/fixtures";
import { eventStream, fail, mockServer, Reply } from "@/test/server";

describe("requests", () => {
  it("sends the stored guest token", async () => {
    tokenStore.set("abc");
    const server = mockServer();
    await api.farms();
    expect(server.calls[0].token).toBe("abc");
  });

  it("sends no token header before a session exists", async () => {
    const server = mockServer();
    await api.health();
    expect(server.calls[0].token).toBeNull();
  });

  it("omits empty query values, and asks for fresh weather only when told to", async () => {
    const server = mockServer({ "GET /api/weather/current": {} });
    await api.currentWeather(30.9, 75.85);
    await api.currentWeather(30.9, 75.85, true);
    expect(server.calls[0].query.has("refresh")).toBe(false);
    expect(server.calls[1].query.get("refresh")).toBe("true");
  });

  it("resolves a 204 to nothing", async () => {
    mockServer({ "DELETE /api/farms/f1": new Reply(204) });
    await expect(api.deleteFarm("f1")).resolves.toBeUndefined();
  });
});

describe("errors", () => {
  it("reads the server's error envelope", async () => {
    mockServer({
      "GET /api/farms": new Reply(422, {
        error: {
          code: "validation_failed",
          message: "Check the form.",
          request_id: "req-9",
          fields: [{ field: "latitude", problem: "Too large" }],
        },
      }),
    });
    const error = await api.farms().catch((caught) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      code: "validation_failed",
      message: "Check the form.",
      status: 422,
      requestId: "req-9",
      fields: [{ field: "latitude", problem: "Too large" }],
    });
  });

  it("calls a non-JSON gateway error unreachable and hides the body", async () => {
    mockServer({ "GET /api/health": new Response("<html>nginx stack trace</html>", { status: 502 }) });
    const error = await api.health().catch((caught) => caught);
    expect(error.code).toBe("server_unreachable");
    expect(error.message).not.toContain("nginx");
  });

  it("turns a failed connection into a network error", async () => {
    vi.stubGlobal("fetch", async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(api.health()).rejects.toMatchObject({ code: "network_error" });
  });
});

describe("createSseParser", () => {
  it("handles frames cut across reads", () => {
    const frames: unknown[] = [];
    const parse = createSseParser((frame) => frames.push(frame));
    parse('data: {"type":"st');
    expect(frames).toEqual([]);
    parse('atus"}\n');
    expect(frames).toEqual([]);
    parse('\ndata: {"type":"final"}\n\n');
    expect(frames).toEqual([{ type: "status" }, { type: "final" }]);
  });

  it("ignores comment lines and joins multi-line data", () => {
    const frames: unknown[] = [];
    const parse = createSseParser((frame) => frames.push(frame));
    parse(': keep-alive\n\n');
    parse('data: {"a":\ndata: 1}\n\n');
    expect(frames).toEqual([{ a: 1 }]);
  });
});

describe("streamChat", () => {
  it("passes each event on and resolves with the final answer", async () => {
    const stream = eventStream();
    mockServer({ "POST /api/agent/chat/stream": stream.response });
    const events: string[] = [];
    const running = streamChat({ message: "Hello" }, (event) => events.push(event.type));
    stream.push({ type: "status", stage: "thinking" });
    stream.push({ type: "final", response: chatResponse });
    stream.close();
    await expect(running).resolves.toEqual(chatResponse);
    expect(events).toEqual(["status", "final"]);
  });

  it("rejects with the code from an error frame", async () => {
    const stream = eventStream();
    mockServer({ "POST /api/agent/chat/stream": stream.response });
    const running = streamChat({ message: "Hello" }, () => {});
    stream.push({ type: "error", code: "agent_unavailable", message: "The assistant is unavailable." });
    stream.close();
    await expect(running).rejects.toMatchObject({
      code: "agent_unavailable",
      message: "The assistant is unavailable.",
    });
  });

  it("rejects when the stream ends without an answer", async () => {
    const stream = eventStream();
    mockServer({ "POST /api/agent/chat/stream": stream.response });
    const running = streamChat({ message: "Hello" }, () => {});
    stream.push({ type: "status", stage: "thinking" });
    stream.close();
    await expect(running).rejects.toMatchObject({ code: "agent_unavailable" });
  });

  it("rejects before streaming when the server refuses the request", async () => {
    mockServer({ "POST /api/agent/chat/stream": fail(503, "agent_not_configured", "No key.") });
    await expect(streamChat({ message: "Hello" }, () => {})).rejects.toMatchObject({
      code: "agent_not_configured",
      status: 503,
    });
  });
});
