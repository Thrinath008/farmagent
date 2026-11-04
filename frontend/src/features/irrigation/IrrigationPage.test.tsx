import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { farm, farmCrop, irrigationNoWeather, irrigationResponse } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { deferred, fail, mockServer } from "@/test/server";
import { IrrigationPage } from "./IrrigationPage";

const submit = () => screen.findByRole("button", { name: "Assess irrigation" });

describe("IrrigationPage", () => {
  it("starts from what the farmer has already entered", async () => {
    mockServer();
    renderPage(<IrrigationPage />);
    await waitFor(() => expect(screen.getByRole("combobox", { name: /^Crop/ })).toHaveTextContent("Wheat"));
    expect(screen.getByRole("combobox", { name: /^Growth stage/ })).toHaveTextContent("Tillering");
    expect(screen.getByRole("combobox", { name: /^Soil type/ })).toHaveTextContent("Loam");
  });

  it("does not pretend to know the soil moisture", async () => {
    mockServer();
    renderPage(<IrrigationPage />);
    expect(await screen.findByRole("combobox", { name: /^Soil moisture/ })).toHaveTextContent("I have not checked");
  });

  it("shows progress, then the assessment and how it was decided", async () => {
    const answer = deferred<unknown>();
    const server = mockServer({ "POST /api/irrigation/assess": () => answer.promise });
    const { user } = renderPage(<IrrigationPage />);
    await user.click(await submit());

    expect(await screen.findByText("Retrieving weather and assessing irrigation")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Checking the weather…" })).toBeDisabled();

    answer.resolve(irrigationResponse);
    expect(await screen.findByTestId("irrigation-result")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Consider postponing irrigation" })).toBeInTheDocument();
    expect(screen.getByTestId("ledger-score")).toHaveTextContent("−1");
    expect(screen.getByText("Live weather")).toBeInTheDocument();

    expect(server.to("POST", "/api/irrigation/assess")[0].body).toMatchObject({
      farm_id: farm.id,
      farm_crop_id: farmCrop.id,
      crop: "wheat",
      growth_stage: "tillering",
      soil_moisture: "unknown",
      recent_rainfall_mm: null,
    });
  });

  it("sends the farm, not coordinates or weather, so the server looks the weather up itself", async () => {
    const server = mockServer({ "POST /api/irrigation/assess": irrigationResponse });
    const { user } = renderPage(<IrrigationPage />);
    await user.click(await submit());
    await screen.findByTestId("irrigation-result");
    const body = server.to("POST", "/api/irrigation/assess")[0].body as Record<string, unknown>;
    expect(body.latitude).toBeNull();
    expect(body.longitude).toBeNull();
    expect(Object.keys(body).some((key) => key.includes("weather") || key.includes("temperature"))).toBe(false);
  });

  it("gives no recommendation when the weather could not be retrieved", async () => {
    mockServer({ "POST /api/irrigation/assess": irrigationNoWeather });
    const { user } = renderPage(<IrrigationPage />);
    await user.click(await submit());
    await screen.findByTestId("irrigation-result");

    expect(screen.getByText("Insufficient information")).toBeInTheDocument();
    expect(screen.getByText("No weather data")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Live weather could not be retrieved");
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
    expect(screen.queryByText("Weather used for this assessment")).not.toBeInTheDocument();
  });

  it("does not offer to save a result that recommends nothing", async () => {
    mockServer({ "POST /api/irrigation/assess": irrigationNoWeather });
    const { user } = renderPage(<IrrigationPage />);
    await user.click(await submit());
    await screen.findByTestId("irrigation-result");
    expect(screen.queryByRole("button", { name: "Save to history" })).not.toBeInTheDocument();
  });

  it("saves a real assessment to history, once", async () => {
    const server = mockServer({
      "POST /api/irrigation/assess": irrigationResponse,
      "POST /api/recommendations": {},
    });
    const { user } = renderPage(<IrrigationPage />);
    await user.click(await submit());
    await user.click(await screen.findByRole("button", { name: "Save to history" }));
    expect(await screen.findByRole("button", { name: "Saved to history" })).toBeDisabled();
    expect(server.to("POST", "/api/recommendations")[0].body).toMatchObject({
      origin: "irrigation_advisor",
      farm_id: farm.id,
      crop: "wheat",
    });
  });

  it("shows a failure with a working retry", async () => {
    let attempts = 0;
    mockServer({
      "POST /api/irrigation/assess": () =>
        ++attempts === 1 ? fail(500, "internal_error", "Something failed on the server.") : irrigationResponse,
    });
    const { user } = renderPage(<IrrigationPage />);
    await user.click(await submit());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something failed on the server.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByTestId("irrigation-result")).toBeInTheDocument());
  });
});
