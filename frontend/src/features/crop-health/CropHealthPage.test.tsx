import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { pestNoWeather, pestResponse } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { fail, mockServer } from "@/test/server";
import { CropHealthPage } from "./CropHealthPage";

const check = () => screen.findByRole("button", { name: "Check weather-related risk" });

describe("CropHealthPage", () => {
  it("says it is not a diagnosis before any result", async () => {
    mockServer();
    renderPage(<CropHealthPage />);
    expect(await screen.findByTestId("diagnosis-disclaimer")).toHaveTextContent("not a plant disease diagnosis");
  });

  it("presents risk as favourable conditions, with what to scout for", async () => {
    mockServer({ "POST /api/pest-risk/assess": pestResponse });
    const { user } = renderPage(<CropHealthPage />);
    await user.click(await check());
    await screen.findByTestId("risk-result");
    const risk = within(screen.getByTestId("risk-yellow_rust"));
    expect(risk.getByText("Yellow rust")).toBeInTheDocument();
    expect(screen.getByText(/does not mean it is in your field/)).toBeInTheDocument();
    expect(screen.getByTestId("diagnosis-disclaimer")).toBeInTheDocument();
  });

  it("recommends no pesticide, dose or treatment", async () => {
    mockServer({ "POST /api/pest-risk/assess": pestResponse });
    const { user } = renderPage(<CropHealthPage />);
    await user.click(await check());
    const result = await screen.findByTestId("risk-result");
    expect(result.textContent).not.toMatch(/\b(spray|fungicide|insecticide|pesticide|dosage|ml\/|g\/acre)\b/i);
  });

  it("assesses nothing when the weather is unavailable, and says why", async () => {
    mockServer({ "POST /api/pest-risk/assess": pestNoWeather });
    const { user } = renderPage(<CropHealthPage />);
    await user.click(await check());
    await screen.findByTestId("risk-result");
    expect(screen.getByRole("alert")).toHaveTextContent("Live weather is not connected");
    expect(screen.getByText("No weather data")).toBeInTheDocument();
    expect(screen.queryByText("Live weather")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save to history" })).not.toBeInTheDocument();
  });

  it("shows a failure with a retry", async () => {
    mockServer({ "POST /api/pest-risk/assess": fail(500, "internal_error", "Something failed on the server.") });
    const { user } = renderPage(<CropHealthPage />);
    await user.click(await check());
    expect(await screen.findByRole("alert")).toHaveTextContent("Something failed on the server.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
