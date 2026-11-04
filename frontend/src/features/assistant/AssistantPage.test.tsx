import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { chatResponse, conversationDetail, health } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { eventStream, fail, mockServer } from "@/test/server";
import { AssistantPage } from "./AssistantPage";

const PATHS = ["/assistant", "/assistant/:conversationId"];
const open = (route = "/assistant") => renderPage(<AssistantPage />, { route, paths: PATHS });
const STREAM = "POST /api/agent/chat/stream";
const STORED = "GET /api/conversations/conv-1";

describe("AssistantPage", () => {
  it("offers example questions in an empty conversation", async () => {
    mockServer();
    open();
    const list = await screen.findByRole("list", { name: "Suggested questions" });
    expect(within(list).getByRole("button", { name: "Should I irrigate my wheat field today?" })).toBeInTheDocument();
  });

  it("shows each tool as it runs, then the final answer", async () => {
    const stream = eventStream();
    const server = mockServer({ [STREAM]: stream.response, [STORED]: conversationDetail() });
    const { user } = open();

    await user.type(await screen.findByLabelText("Your question"), "Should I irrigate?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const turn = await screen.findByTestId("current-turn");
    expect(within(turn).getByText("Should I irrigate?")).toBeInTheDocument();
    expect(within(turn).getByText("Working out what to check…")).toBeInTheDocument();

    stream.push({ type: "tool_start", id: "t1", name: "get_current_weather" });
    expect(await within(turn).findByText("Checked current weather")).toBeInTheDocument();
    expect(within(turn).queryByText("Live weather")).not.toBeInTheDocument();

    stream.push({
      type: "tool_end",
      id: "t1",
      name: "get_current_weather",
      ok: true,
      duration_ms: 120,
      error_code: null,
      provenance: "live",
    });
    expect(await within(turn).findByText("Live weather")).toBeInTheDocument();
    expect(within(turn).getByText("Writing the answer…")).toBeInTheDocument();

    stream.push({ type: "final", response: chatResponse });
    stream.close();

    expect(await screen.findByTestId("advice-card")).toHaveTextContent("Rain may do some of the work.");
    expect(screen.queryByTestId("current-turn")).not.toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/assistant/conv-1");
    expect(server.to("POST", "/api/agent/chat/stream")[0].body).toMatchObject({
      message: "Should I irrigate?",
      conversation_id: null,
      farm_id: "farm-1",
    });
  });

  it("marks a failed tool without claiming its weather", async () => {
    const stream = eventStream();
    mockServer({ [STREAM]: stream.response });
    const { user } = open();
    await user.type(await screen.findByLabelText("Your question"), "Weather?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    stream.push({ type: "tool_start", id: "t1", name: "get_current_weather" });
    stream.push({
      type: "tool_end",
      id: "t1",
      name: "get_current_weather",
      ok: false,
      duration_ms: 90,
      error_code: "weather_unavailable",
      provenance: null,
    });
    const turn = await screen.findByTestId("current-turn");
    await within(turn).findByText("Checked current weather");
    await waitFor(() => expect(within(turn).queryByText("Live weather")).not.toBeInTheDocument());
    expect(within(turn).queryByText("Cached")).not.toBeInTheDocument();
  });

  it("keeps the question after a failure, and retries it", async () => {
    let attempts = 0;
    const server = mockServer({
      [STREAM]: () => {
        attempts += 1;
        if (attempts === 1) return fail(503, "agent_unavailable", "The AI assistant is unavailable right now.");
        const stream = eventStream();
        stream.push({ type: "final", response: chatResponse });
        stream.close();
        return stream.response;
      },
      [STORED]: conversationDetail(),
    });
    const { user } = open();
    await user.type(await screen.findByLabelText("Your question"), "Should I irrigate?");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("The assistant could not finish");
    expect(alert).toHaveTextContent("The AI assistant is unavailable right now.");
    expect(screen.getByLabelText("Your question")).toHaveValue("Should I irrigate?");

    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("advice-card")).toBeInTheDocument();
    expect(server.to("POST", "/api/agent/chat/stream")).toHaveLength(2);
  });

  it("disables the composer and hides suggestions when no key is set", async () => {
    mockServer({ "GET /api/health": { ...health, ai_configured: false, ai_model: null } });
    open();
    expect(await screen.findByText("The AI assistant is not connected")).toBeInTheDocument();
    expect(screen.getByLabelText("Your question")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    expect(screen.queryByRole("list", { name: "Suggested questions" })).not.toBeInTheDocument();
  });

  it("does not send an empty question", async () => {
    const server = mockServer();
    const { user } = open();
    await screen.findByLabelText("Your question");
    expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
    await user.type(screen.getByLabelText("Your question"), "   {Enter}");
    expect(server.to("POST", "/api/agent/chat/stream")).toHaveLength(0);
  });

  it("stops calling an old conversation's weather live", async () => {
    const old = new Date(Date.now() - 3 * 3_600_000).toISOString();
    mockServer({ [STORED]: conversationDetail(old) });
    open("/assistant/conv-1");
    await screen.findByTestId("advice-card");
    expect(screen.getByTestId("weather-context")).toHaveTextContent("Live at the time");
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
  });

  it("shows a failed conversation load", async () => {
    mockServer({ [STORED]: fail(404, "conversation_not_found", "That conversation no longer exists.") });
    open("/assistant/conv-1");
    expect(await screen.findByRole("alert")).toHaveTextContent("That conversation no longer exists.");
  });
});
