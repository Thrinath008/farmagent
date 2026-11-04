import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ONBOARDING_SKIPPED } from "@/lib/labels";
import { currentWeather, farm, farmCrop, forecast, irrigationResponse, pestNoWeather, pestResponse, schedule } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { fail, mockServer, pending } from "@/test/server";
import { OverviewPage } from "./OverviewPage";

const live = {
  "GET /api/weather/current": currentWeather(),
  "GET /api/weather/forecast": forecast(),
  "POST /api/irrigation/assess": irrigationResponse,
  "POST /api/pest-risk/assess": pestResponse,
};

describe("OverviewPage", () => {
  it("sends a new guest with no farm to onboarding", async () => {
    mockServer({ "GET /api/farms": [] });
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/welcome"));
  });

  it("does not send a guest back after they skipped", async () => {
    localStorage.setItem(ONBOARDING_SKIPPED, "1");
    mockServer({ "GET /api/farms": [] });
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    expect(await screen.findByRole("link", { name: /Add|Set up/ })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent("/");
    expect(screen.getByTestId("location")).not.toHaveTextContent("/welcome");
  });

  it("shows a loading state while farms load", async () => {
    mockServer({ "GET /api/farms": pending });
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    expect(await screen.findByText("Loading your farm")).toBeInTheDocument();
  });

  it("shows the farm's conditions with their provenance", async () => {
    mockServer(live);
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    expect(await screen.findByText("21°C")).toBeInTheDocument();
    expect(screen.getAllByText("Live weather").length).toBeGreaterThan(0);
  });

  it("labels every weather-based panel with where its weather came from", async () => {
    mockServer({
      "GET /api/weather/current": currentWeather({ provenance: "cached", age_seconds: 120 }),
      "GET /api/weather/forecast": forecast({ provenance: "cached", age_seconds: 120 }),
      "POST /api/irrigation/assess": {
        ...irrigationResponse,
        assessment: { ...irrigationResponse.assessment, weather_provenance: "cached" },
      },
      "POST /api/pest-risk/assess": pestNoWeather,
    });
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    const panel = async (name: string) => screen.findByRole("region", { name });
    expect(await within(await panel("Forecast")).findByText("Cached · 2 min ago")).toBeInTheDocument();
    expect(await within(await panel("Irrigation status")).findByText(/^Cached/)).toBeInTheDocument();
    expect(await within(await panel("Weather-related crop risk")).findByText("No weather data")).toBeInTheDocument();
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
  });

  it("stops calling the forecast live when a refresh fails", async () => {
    let attempts = 0;
    mockServer({
      ...live,
      "GET /api/weather/current": () =>
        ++attempts === 1 ? currentWeather() : fail(503, "weather_unavailable", "Down."),
    });
    const { user } = renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    const forecastPanel = await screen.findByRole("region", { name: "Forecast" });
    expect(await within(forecastPanel).findByText("Live weather")).toBeInTheDocument();

    await user.click(await screen.findByRole("button", { name: "Refresh weather" }));
    await waitFor(() => expect(within(forecastPanel).queryByText("Live weather")).not.toBeInTheDocument());
    expect(screen.getByRole("region", { name: "Weather now" })).not.toHaveTextContent("Live weather");
  });

  it("explains a weather failure and claims nothing live", async () => {
    const down = fail(503, "weather_unavailable", "Down.");
    mockServer({
      ...live,
      "GET /api/weather/current": down,
      "GET /api/weather/forecast": down,
      "POST /api/irrigation/assess": down,
      "POST /api/pest-risk/assess": down,
    });
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    expect((await screen.findAllByText("Live weather could not be retrieved")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
  });

  it("shows the crop's season when it has a schedule", async () => {
    mockServer({
      ...live,
      "GET /api/farms": [{ ...farm, crops: [{ ...farmCrop, irrigation_schedule: schedule }] }],
    });
    renderPage(<OverviewPage />, { route: "/", paths: ["/"] });
    expect(await screen.findByTestId("season-track")).toBeInTheDocument();
  });
});
