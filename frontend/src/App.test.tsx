import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "@/App";
import { currentWeather, farm, forecast, health } from "@/test/fixtures";
import { renderApp } from "@/test/render";
import { deferred, fail, mockServer } from "@/test/server";

const weatherRoutes = {
  "GET /api/weather/current": currentWeather(),
  "GET /api/weather/forecast": forecast(),
  "GET /api/health": health,
};

describe("App shell", () => {
  it("keeps the farm switcher working when a page's code and the farms load together", async () => {
    // Opening a deep link: the shell mounts first, then the lazy page suspends while farms arrive.
    // A shell that suspends with the page never updates, and leaves the switcher blank for good.
    const farms = deferred<unknown>();
    mockServer({ ...weatherRoutes, "GET /api/farms": () => farms.promise });
    renderApp(<App />, "/weather");

    const sidebar = within(await screen.findByRole("complementary"));
    expect(sidebar.queryByRole("combobox", { name: "Farm" })).not.toBeInTheDocument();
    farms.resolve([farm]);

    expect(await sidebar.findByRole("combobox", { name: "Farm" })).toHaveTextContent("North field");
    expect(await screen.findByRole("heading", { name: "Weather Intelligence" })).toBeInTheDocument();
  });

  it("keeps the navigation on screen while a page loads", async () => {
    mockServer(weatherRoutes);
    renderApp(<App />, "/farm");
    expect(await screen.findByRole("navigation", { name: "Main" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "My Farm" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Main" })).toBeInTheDocument();
  });

  it("offers a way out of an unknown address", async () => {
    mockServer();
    renderApp(<App />, "/no-such-page");
    expect(await screen.findByText("That page does not exist")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to the overview" })).toHaveAttribute("href", "/");
  });

  it("explains a failed session, and still offers the Scenario Lab", async () => {
    mockServer({
      "GET /api/session/me": fail(503, "database_unavailable", "The database is unavailable."),
      "GET /api/farms": [],
    });
    renderApp(<App />, "/weather");
    expect(await screen.findByText("FarmAgent could not start your session")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Scenario Lab, which works without a session/ })).toHaveAttribute(
      "href",
      "/scenario-lab",
    );
  });

  it("opens the Scenario Lab even when the session cannot start", async () => {
    const server = mockServer({
      "GET /api/session/me": fail(503, "database_unavailable", "The database is unavailable."),
      "GET /api/scenarios": [],
    });
    renderApp(<App />, "/scenario-lab");
    expect(await screen.findByRole("heading", { name: "Scenario Lab" })).toBeInTheDocument();
    await waitFor(() => expect(server.to("GET", "/api/scenarios")).toHaveLength(1));
  });
});
