import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/services/api";
import { EmptyState, ErrorState, LoadingState } from "./States";

const show = (error: unknown, onRetry?: () => void) =>
  render(
    <MemoryRouter>
      <ErrorState error={error} onRetry={onRetry} />
    </MemoryRouter>,
  );

describe("ErrorState", () => {
  it("explains a missing weather key, with no retry and a way to the Scenario Lab", () => {
    show(new ApiError("weather_not_configured", "internal text"), () => {});
    expect(screen.getByRole("alert")).toHaveTextContent("Live weather is not connected");
    expect(screen.getByRole("alert")).toHaveTextContent("No substitute data is used");
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open the Scenario Lab" })).toHaveAttribute("href", "/scenario-lab");
  });

  it("offers a retry for a provider outage, and it works", async () => {
    const retry = vi.fn();
    show(new ApiError("weather_unavailable", "Down"), retry);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
    expect(screen.getByRole("link", { name: "Open the Scenario Lab" })).toBeInTheDocument();
  });

  it("shows no retry button when nothing can retry", () => {
    show(new ApiError("weather_unavailable", "Down"));
    expect(screen.queryByRole("button", { name: "Try again" })).not.toBeInTheDocument();
  });

  it("uses the server's message for other API errors, with the reference", () => {
    show(new ApiError("farm_not_found", "That farm no longer exists.", 404, "req-7"));
    expect(screen.getByRole("alert")).toHaveTextContent("That farm no longer exists.");
    expect(screen.getByRole("alert")).toHaveTextContent("Reference req-7");
  });

  it("never prints an unexpected exception", () => {
    show(new Error("TypeError: cannot read secret_key of undefined"));
    expect(screen.getByRole("alert")).not.toHaveTextContent("secret_key");
    expect(screen.getByRole("alert")).toHaveTextContent("That did not work");
  });
});

describe("EmptyState and LoadingState", () => {
  it("shows the title, the direction and the action", () => {
    render(
      <EmptyState title="No farms yet" action={<button type="button">Add</button>}>
        Add a location.
      </EmptyState>,
    );
    expect(screen.getByText("No farms yet")).toBeInTheDocument();
    expect(screen.getByText("Add a location.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add" })).toBeInTheDocument();
  });

  it("announces what is loading", () => {
    render(<LoadingState label="Loading your farms" />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading your farms");
  });
});
