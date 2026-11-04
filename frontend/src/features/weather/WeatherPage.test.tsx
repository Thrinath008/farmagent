import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { currentWeather, farm, forecast } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { fail, mockServer, pending } from "@/test/server";
import { WeatherPage } from "./WeatherPage";

const ok = { "GET /api/weather/current": currentWeather(), "GET /api/weather/forecast": forecast() };

describe("WeatherPage", () => {
  it("shows a loading state while the weather is on its way", async () => {
    mockServer({ "GET /api/weather/current": pending, "GET /api/weather/forecast": pending });
    renderPage(<WeatherPage />);
    expect(await screen.findByText("Loading current weather")).toBeInTheDocument();
    expect(screen.getByText("Loading the forecast")).toBeInTheDocument();
  });

  it("labels live readings as live, and names the source", async () => {
    mockServer(ok);
    renderPage(<WeatherPage />);
    expect(await screen.findByText("21°C")).toBeInTheDocument();
    expect(screen.getAllByText("Live weather").length).toBeGreaterThan(0);
    expect(screen.getByTestId("last-updated")).toHaveTextContent("OpenWeatherMap");
  });

  it("labels cached readings as cached and never as live", async () => {
    mockServer({
      "GET /api/weather/current": currentWeather({ provenance: "cached", age_seconds: 300 }),
      "GET /api/weather/forecast": forecast({ provenance: "cached", age_seconds: 300 }),
    });
    renderPage(<WeatherPage />);
    expect((await screen.findAllByText(/^Cached · 5 min ago$/)).length).toBe(2);
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
  });

  it("shows the server's warning when the data could not be refreshed", async () => {
    const warning = "Live weather could not be refreshed. This data was retrieved 8 minutes ago and may be out of date.";
    mockServer({
      "GET /api/weather/current": currentWeather({ provenance: "cached", age_seconds: 480, warning }),
      "GET /api/weather/forecast": forecast({ provenance: "cached", age_seconds: 480 }),
    });
    renderPage(<WeatherPage />);
    expect(await screen.findByText(warning)).toBeInTheDocument();
  });

  it("says when no key is set, shows nothing live, and links to the Scenario Lab", async () => {
    const down = fail(503, "weather_not_configured", "No key.");
    mockServer({ "GET /api/weather/current": down, "GET /api/weather/forecast": down });
    renderPage(<WeatherPage />);
    expect((await screen.findAllByText("Live weather is not connected")).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Open the Scenario Lab" })[0]).toHaveAttribute("href", "/scenario-lab");
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
    expect(screen.queryByText("21°C")).not.toBeInTheDocument();
  });

  it("offers a retry after an outage, and shows the weather once it works", async () => {
    let attempts = 0;
    mockServer({
      "GET /api/weather/current": () =>
        ++attempts === 1 ? fail(503, "weather_unavailable", "Down.") : currentWeather(),
      "GET /api/weather/forecast": forecast(),
    });
    const { user } = renderPage(<WeatherPage />);
    const alert = await screen.findByRole("alert");
    await user.click(within(alert).getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("21°C")).toBeInTheDocument();
  });

  it("asks the provider afresh only when the farmer presses refresh", async () => {
    const server = mockServer(ok);
    const { user } = renderPage(<WeatherPage />);
    await screen.findByText("21°C");
    expect(server.to("GET", "/api/weather/current")[0].query.has("refresh")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Refresh weather" }));
    await waitFor(() => expect(server.to("GET", "/api/weather/current")).toHaveLength(2));
    expect(server.to("GET", "/api/weather/current")[1].query.get("refresh")).toBe("true");
    expect(server.to("GET", "/api/weather/forecast")[1].query.get("refresh")).toBe("true");
  });

  it("stops claiming live when a refresh fails", async () => {
    let attempts = 0;
    mockServer({
      "GET /api/weather/current": () =>
        ++attempts === 1 ? currentWeather() : fail(503, "weather_unavailable", "Down."),
      "GET /api/weather/forecast": forecast(),
    });
    const { user } = renderPage(<WeatherPage />);
    await screen.findByText("21°C");
    expect(screen.getAllByText("Live weather").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Refresh weather" }));
    expect(await screen.findByText("The refresh failed")).toBeInTheDocument();
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
    expect(screen.getByText("21°C")).toBeInTheDocument();
  });

  it("keeps rain amount and rain chance as separate, separately labelled charts", async () => {
    mockServer(ok);
    renderPage(<WeatherPage />);
    expect(await screen.findByRole("figure", { name: /^Expected rainfall amount/ })).toBeInTheDocument();
    const chance = screen.getByRole("figure", { name: /^Chance of rain as a percentage/ });
    expect(chance).toHaveTextContent("says how likely rain is, not how much");
  });

  it("lists every forecast value in a table, with the same separation", async () => {
    mockServer(ok);
    renderPage(<WeatherPage />);
    const table = await screen.findByRole("table", { hidden: true });
    expect(within(table).getByText(/Expected rain/)).toBeInTheDocument();
    expect(within(table).getByText(/Chance of rain/)).toBeInTheDocument();
    expect(within(table).getByText("2.5 mm")).toBeInTheDocument();
    expect(within(table).getByText("70%")).toBeInTheDocument();
  });

  it("asks for a location when the farm has none, rather than guessing one", async () => {
    const server = mockServer({ "GET /api/farms": [{ ...farm, latitude: null, longitude: null }] });
    renderPage(<WeatherPage />);
    expect(await screen.findByText("Choose a location to see its weather")).toBeInTheDocument();
    expect(server.to("GET", "/api/weather/current")).toHaveLength(0);
  });
});
