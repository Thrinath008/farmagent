import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { advice, health, scenarioRun, scenarios } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { fail, mockServer, pending } from "@/test/server";
import { ScenarioLabPage } from "./ScenarioLabPage";

const routes = { "GET /api/scenarios": scenarios, "POST /api/scenarios/run": scenarioRun };
const runButton = () => screen.findByRole("button", { name: "Run Both Scenarios" });

describe("ScenarioLabPage", () => {
  it("labels everything as simulated before anything runs", async () => {
    mockServer(routes);
    renderPage(<ScenarioLabPage />);
    expect(await screen.findByTestId("scenario-A")).toHaveTextContent("Simulated");
    expect(screen.getByTestId("scenario-B")).toHaveTextContent("Simulated");
    expect(screen.getByText(/It is not real weather/)).toBeInTheDocument();
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
  });

  it("shows a loading state, then a retry when the scenarios cannot load", async () => {
    mockServer({ "GET /api/scenarios": pending });
    const first = renderPage(<ScenarioLabPage />);
    expect(await screen.findByText("Loading scenarios")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run Both Scenarios" })).toBeDisabled();
    first.unmount();

    mockServer({ "GET /api/scenarios": fail(500, "internal_error", "It failed.") });
    renderPage(<ScenarioLabPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("It failed.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("runs both and compares them side by side, still labelled simulated", async () => {
    const server = mockServer(routes);
    const { user } = renderPage(<ScenarioLabPage />);
    await user.click(await runButton());
    await screen.findByTestId("scenario-results");

    expect(within(screen.getByTestId("outcome-A")).getByText("Hold off for the rain")).toBeInTheDocument();
    expect(within(screen.getByTestId("outcome-B")).getByText("Consider irrigating soon")).toBeInTheDocument();
    expect(screen.getByTestId("outcome-A")).toHaveTextContent("Simulated");
    expect(screen.getByTestId("outcome-B")).toHaveTextContent("Simulated");
    expect(screen.getByTestId("comparison-forecast_rain")).toHaveTextContent("Forecast rain");
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
    expect(server.to("POST", "/api/scenarios/run")[0].body).toEqual({ include_ai: false });
  });

  it("asks Claude only when the farmer ticks the box", async () => {
    const withClaude = {
      ...scenarioRun,
      results: scenarioRun.results.map((result) => ({
        ...result,
        ai: { status: "completed" as const, advice, tool_log: [], message: null, code: null },
      })),
    };
    const server = mockServer({ ...routes, "POST /api/scenarios/run": withClaude });
    const { user } = renderPage(<ScenarioLabPage />);
    await runButton();
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
    await user.click(screen.getByRole("checkbox"));
    await user.click(await runButton());
    await screen.findByTestId("scenario-results");
    expect(server.to("POST", "/api/scenarios/run")[0].body).toEqual({ include_ai: true });
    expect(within(screen.getByTestId("recommendation-A")).getByText("Claude's explanation")).toBeInTheDocument();
    expect(within(screen.getByTestId("recommendation-A")).getByText("From the rule-based engine")).toBeInTheDocument();
  });

  it("still shows the engine's result when Claude is unavailable", async () => {
    const claudeDown = {
      ...scenarioRun,
      results: scenarioRun.results.map((result) => ({
        ...result,
        ai: {
          status: "unavailable" as const,
          advice: null,
          tool_log: [],
          message: "The AI assistant is unavailable right now.",
          code: "agent_unavailable",
        },
      })),
    };
    mockServer({ ...routes, "POST /api/scenarios/run": claudeDown });
    const { user } = renderPage(<ScenarioLabPage />);
    await runButton();
    await waitFor(() => expect(screen.getByRole("checkbox")).toBeEnabled());
    await user.click(screen.getByRole("checkbox"));
    await user.click(await runButton());
    await screen.findByTestId("scenario-results");
    expect(within(screen.getByTestId("recommendation-A")).getByRole("status")).toHaveTextContent(
      "The rule-based result above is unaffected",
    );
    expect(screen.getByTestId("outcome-A")).toHaveTextContent("Hold off for the rain");
  });

  it("disables the Claude option when no key is set, and runs the engine anyway", async () => {
    const server = mockServer({ ...routes, "GET /api/health": { ...health, ai_configured: false, ai_model: null } });
    const { user } = renderPage(<ScenarioLabPage />);
    expect(await screen.findByText(/needs an Anthropic key on the server/)).toBeInTheDocument();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    await user.click(await runButton());
    await screen.findByTestId("scenario-results");
    expect(server.to("POST", "/api/scenarios/run")[0].body).toEqual({ include_ai: false });
  });

  it("shows a failed run with a working retry", async () => {
    let attempts = 0;
    mockServer({
      "GET /api/scenarios": scenarios,
      "POST /api/scenarios/run": () => (++attempts === 1 ? fail(500, "internal_error", "The run failed.") : scenarioRun),
    });
    const { user } = renderPage(<ScenarioLabPage />);
    await user.click(await runButton());
    expect(await screen.findByRole("alert")).toHaveTextContent("The run failed.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByTestId("scenario-results")).toBeInTheDocument();
  });
});
