import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { recommendation } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { fail, mockServer, pending, Reply } from "@/test/server";
import { HistoryPage } from "./HistoryPage";

describe("HistoryPage", () => {
  it("shows loading, then an empty state with a next step", async () => {
    mockServer({ "GET /api/recommendations": pending });
    const loading = renderPage(<HistoryPage />);
    expect(await screen.findByText("Loading your history")).toBeInTheDocument();
    loading.unmount();

    mockServer({ "GET /api/recommendations": [] });
    renderPage(<HistoryPage />);
    expect(await screen.findByText("No saved recommendations yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the Irrigation Advisor" })).toHaveAttribute("href", "/irrigation");
  });

  it("shows a failure with a retry", async () => {
    mockServer({ "GET /api/recommendations": fail(500, "internal_error", "History could not load.") });
    renderPage(<HistoryPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("History could not load.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("never calls stored weather live, in the row or once opened", async () => {
    mockServer({ "GET /api/recommendations": [recommendation] });
    const { user } = renderPage(<HistoryPage />);
    const row = within(await screen.findByTestId(`recommendation-${recommendation.id}`));
    expect(row.getByText("Live at the time")).toBeInTheDocument();

    await user.click(row.getByRole("button", { name: /Consider postponing irrigation/ }));
    expect(within(await screen.findByTestId("weather-context")).getByText("Live at the time")).toBeInTheDocument();
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
  });

  it("filters on the server, and clears back to everything", async () => {
    const server = mockServer({ "GET /api/recommendations": (call: { query: URLSearchParams }) => (call.query.get("intent") ? [] : [recommendation]) });
    const { user } = renderPage(<HistoryPage />);
    await screen.findByTestId(`recommendation-${recommendation.id}`);

    await user.click(screen.getByRole("combobox", { name: "Topic" }));
    await user.click(await screen.findByRole("option", { name: "Weather" }));
    expect(await screen.findByText("Nothing matches these filters")).toBeInTheDocument();
    expect(server.to("GET", "/api/recommendations").at(-1)?.query.get("intent")).toBe("weather_question");

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByTestId(`recommendation-${recommendation.id}`)).toBeInTheDocument();
  });

  it("asks before deleting", async () => {
    const server = mockServer({
      "GET /api/recommendations": [recommendation],
      "DELETE /api/recommendations/rec-1": new Reply(204),
    });
    const { user } = renderPage(<HistoryPage />);
    await user.click(await screen.findByRole("button", { name: "Delete this recommendation" }));
    expect(server.to("DELETE", "/api/recommendations/rec-1")).toHaveLength(0);
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(server.to("DELETE", "/api/recommendations/rec-1")).toHaveLength(1));
  });
});
