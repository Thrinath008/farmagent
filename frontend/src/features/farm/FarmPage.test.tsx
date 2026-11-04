import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { farm, farmCrop, schedule } from "@/test/fixtures";
import { renderPage } from "@/test/render";
import { fail, mockServer, pending, Reply } from "@/test/server";
import { FarmPage } from "./FarmPage";

const CROP_URL = `/api/farms/${farm.id}/crops/${farmCrop.id}`;

describe("FarmPage", () => {
  it("shows a loading state, then an empty state with a way forward", async () => {
    mockServer({ "GET /api/farms": pending });
    const loading = renderPage(<FarmPage />);
    expect(await screen.findByText("Loading your farms")).toBeInTheDocument();
    loading.unmount();

    mockServer({ "GET /api/farms": [] });
    renderPage(<FarmPage />);
    expect(await screen.findByText("No farms yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add your first farm" })).toBeInTheDocument();
  });

  it("shows a failure to load with a retry", async () => {
    mockServer({ "GET /api/farms": fail(500, "internal_error", "Farms could not load.") });
    renderPage(<FarmPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Farms could not load.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("adds a farm with only what was entered", async () => {
    const server = mockServer({ "POST /api/farms": { ...farm, id: "farm-2", name: "River plot" } });
    const { user } = renderPage(<FarmPage />);
    await screen.findByTestId(`farm-${farm.id}`);
    await user.click(screen.getByRole("button", { name: "Add a farm" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Farm name/), "River plot");
    await user.click(dialog.getByRole("button", { name: "Add farm" }));
    await waitFor(() => expect(server.to("POST", "/api/farms")).toHaveLength(1));
    expect(server.to("POST", "/api/farms")[0].body).toMatchObject({
      name: "River plot",
      latitude: null,
      soil_type: null,
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("asks before deleting a farm, then deletes it", async () => {
    const server = mockServer({ [`DELETE /api/farms/${farm.id}`]: new Reply(204) });
    const { user } = renderPage(<FarmPage />);
    const card = within(await screen.findByTestId(`farm-${farm.id}`));
    await user.click(card.getByRole("button", { name: "Delete" }));
    expect(server.to("DELETE", `/api/farms/${farm.id}`)).toHaveLength(0);

    const dialog = within(await screen.findByRole("alertdialog"));
    expect(dialog.getByText("Delete North field?")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Delete farm" }));
    await waitFor(() => expect(server.to("DELETE", `/api/farms/${farm.id}`)).toHaveLength(1));
  });

  it("does nothing when the farmer cancels a delete", async () => {
    const server = mockServer();
    const { user } = renderPage(<FarmPage />);
    const card = within(await screen.findByTestId(`farm-${farm.id}`));
    await user.click(card.getByRole("button", { name: "Delete" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Keep it" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    expect(server.to("DELETE", `/api/farms/${farm.id}`)).toHaveLength(0);
  });

  it("updates a crop's stage in place", async () => {
    const server = mockServer({ [`PATCH ${CROP_URL}`]: { ...farmCrop, growth_stage: "heading" } });
    const { user } = renderPage(<FarmPage />);
    const row = within(await screen.findByTestId(`crop-${farmCrop.id}`));
    await user.click(await row.findByRole("combobox", { name: "Growth stage" }));
    await user.click(await screen.findByRole("option", { name: "Heading" }));
    await waitFor(() => expect(server.to("PATCH", CROP_URL)).toHaveLength(1));
    expect(server.to("PATCH", CROP_URL)[0].body).toEqual({ growth_stage: "heading" });
  });

  it("clears a stage to null rather than keeping a guess", async () => {
    const server = mockServer({ [`PATCH ${CROP_URL}`]: { ...farmCrop, growth_stage: null } });
    const { user } = renderPage(<FarmPage />);
    const row = within(await screen.findByTestId(`crop-${farmCrop.id}`));
    await user.click(await row.findByRole("combobox", { name: "Growth stage" }));
    await user.click(await screen.findByRole("option", { name: "Not sure" }));
    await waitFor(() => expect(server.to("PATCH", CROP_URL)).toHaveLength(1));
    expect(server.to("PATCH", CROP_URL)[0].body).toEqual({ growth_stage: null });
  });

  it("removes a crop after asking", async () => {
    const server = mockServer({ [`DELETE ${CROP_URL}`]: new Reply(204) });
    const { user } = renderPage(<FarmPage />);
    const row = within(await screen.findByTestId(`crop-${farmCrop.id}`));
    await user.click(row.getByRole("button", { name: "Remove Wheat" }));
    await user.click(within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Remove crop" }));
    await waitFor(() => expect(server.to("DELETE", CROP_URL)).toHaveLength(1));
  });

  it("says when a crop's rules are not available", async () => {
    mockServer({
      "GET /api/farms": [
        { ...farm, crops: [{ ...farmCrop, crop: "rice", crop_name: "Rice", support_level: "planned", growth_stage: null }] },
      ],
    });
    renderPage(<FarmPage />);
    expect(await screen.findByText("Crop-specific rules are not available yet.")).toBeInTheDocument();
  });

  it("lays out the season when there is a schedule", async () => {
    mockServer({
      "GET /api/farms": [{ ...farm, crops: [{ ...farmCrop, sowing_date: schedule.sowing_date, irrigation_schedule: schedule }] }],
    });
    renderPage(<FarmPage />);
    expect(await screen.findByTestId("season-track")).toBeInTheDocument();
    expect(screen.getByText("Wheat irrigation season")).toBeInTheDocument();
  });
});
