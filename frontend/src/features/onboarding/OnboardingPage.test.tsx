import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { farm, user as sessionUser } from "@/test/fixtures";
import { ONBOARDING_SKIPPED } from "@/lib/labels";
import { renderPage } from "@/test/render";
import { fail, mockServer } from "@/test/server";
import { OnboardingPage } from "./OnboardingPage";

const start = () => renderPage(<OnboardingPage />, { route: "/welcome", paths: ["/welcome"] });
const routes = {
  "GET /api/farms": [],
  "PATCH /api/session/me": sessionUser,
  "POST /api/farms": farm,
};

async function continueTo(user: ReturnType<typeof start>["user"], step: string) {
  await user.click(screen.getByRole("button", { name: "Continue" }));
  expect(await screen.findByRole("heading", { name: step })).toBeInTheDocument();
}

describe("OnboardingPage", () => {
  it("lets the farmer skip, and remembers that without creating anything", async () => {
    const server = mockServer(routes);
    const { user } = start();
    await user.click(await screen.findByRole("button", { name: "Skip setup" }));
    expect(screen.getByTestId("location")).toHaveTextContent("/");
    expect(localStorage.getItem(ONBOARDING_SKIPPED)).toBe("1");
    expect(server.to("POST", "/api/farms")).toHaveLength(0);
  });

  it("creates no farm when every step is left empty", async () => {
    const server = mockServer(routes);
    const { user } = start();
    await screen.findByRole("heading", { name: "You" });
    await continueTo(user, "Location");
    await continueTo(user, "Farm");
    await continueTo(user, "Crop");
    await user.click(screen.getByRole("button", { name: "Finish setup" }));
    await waitFor(() => expect(server.to("PATCH", "/api/session/me")).toHaveLength(1));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("/"));
    expect(server.to("POST", "/api/farms")).toHaveLength(0);
  });

  it("sends only what was entered and invents nothing", async () => {
    const server = mockServer(routes);
    const { user } = start();
    await screen.findByRole("heading", { name: "You" });
    await continueTo(user, "Location");
    await continueTo(user, "Farm");
    await user.type(screen.getByLabelText(/^Farm name/), "River plot");
    await continueTo(user, "Crop");
    await user.click(screen.getByRole("button", { name: "Finish setup" }));

    await waitFor(() => expect(server.to("POST", "/api/farms")).toHaveLength(1));
    expect(server.to("POST", "/api/farms")[0].body).toEqual({
      name: "River plot",
      location_name: null,
      state: null,
      country: null,
      latitude: null,
      longitude: null,
      size_value: null,
      area_unit: null,
      soil_type: null,
      crops: [],
    });
  });

  it("stores no made-up name for an unnamed farmer", async () => {
    const server = mockServer(routes);
    const { user } = start();
    await screen.findByRole("heading", { name: "You" });
    await user.type(screen.getByLabelText(/^Your name/), "  ");
    await continueTo(user, "Location");
    await continueTo(user, "Farm");
    await continueTo(user, "Crop");
    await user.click(screen.getByRole("button", { name: "Finish setup" }));
    await waitFor(() => expect(server.to("PATCH", "/api/session/me")).toHaveLength(1));
    expect(server.to("PATCH", "/api/session/me")[0].body).toMatchObject({ display_name: null });
  });

  it("rejects an impossible farm size", async () => {
    mockServer(routes);
    const { user } = start();
    await screen.findByRole("heading", { name: "You" });
    await continueTo(user, "Location");
    await continueTo(user, "Farm");
    await user.type(screen.getByLabelText(/^Farm size/), "-3");
    await user.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("Enter a number above zero, or leave this empty.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Farm" })).toBeInTheDocument();
  });

  it("shows a save failure and stays on the step", async () => {
    mockServer({ ...routes, "PATCH /api/session/me": fail(500, "internal_error", "It could not be saved.") });
    const { user } = start();
    await screen.findByRole("heading", { name: "You" });
    await continueTo(user, "Location");
    await continueTo(user, "Farm");
    await continueTo(user, "Crop");
    await user.click(screen.getByRole("button", { name: "Finish setup" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("It could not be saved.");
    expect(screen.getByTestId("location")).toHaveTextContent("/welcome");
  });
});
