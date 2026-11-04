import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { health, user as sessionUser } from "@/test/fixtures";
import { tokenStore } from "@/services/api";
import { renderPage } from "@/test/render";
import { mockServer, Reply } from "@/test/server";
import { SettingsPage } from "./SettingsPage";

describe("SettingsPage", () => {
  it("reports what the server has, without showing any key", async () => {
    mockServer({ "GET /api/health": { ...health, weather_configured: false, ai_configured: false, ai_model: null } });
    renderPage(<SettingsPage />);
    expect(await screen.findByText("Live weather: not connected")).toBeInTheDocument();
    expect(screen.getByText("AI assistant: not connected")).toBeInTheDocument();
    expect(screen.getByText("Database: connected")).toBeInTheDocument();
  });

  it("says which crops have rules and which do not", async () => {
    mockServer();
    renderPage(<SettingsPage />);
    expect(await screen.findByText("Rules implemented:")).toBeInTheDocument();
    expect(screen.getByText("Planned:")).toBeInTheDocument();
  });

  it("saves the profile", async () => {
    const server = mockServer({ "PATCH /api/session/me": { ...sessionUser, display_name: "Harpreet" } });
    const { user } = renderPage(<SettingsPage />);
    await user.type(await screen.findByLabelText(/^Your name/), "Harpreet");
    await user.click(screen.getByRole("button", { name: "Save profile" }));
    await waitFor(() => expect(server.to("PATCH", "/api/session/me")).toHaveLength(1));
    expect(server.to("PATCH", "/api/session/me")[0].body).toMatchObject({ display_name: "Harpreet" });
  });

  it("deletes all data only after asking, and forgets the session", async () => {
    const server = mockServer({ "DELETE /api/session/me": new Reply(204) });
    const { user } = renderPage(<SettingsPage />, { route: "/settings", paths: ["/settings"] });
    await user.click(await screen.findByRole("button", { name: "Delete all my data" }));
    expect(server.to("DELETE", "/api/session/me")).toHaveLength(0);
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Delete everything" }));
    await waitFor(() => expect(server.to("DELETE", "/api/session/me")).toHaveLength(1));
    await waitFor(() => expect(tokenStore.get()).toBeNull());
  });
});
