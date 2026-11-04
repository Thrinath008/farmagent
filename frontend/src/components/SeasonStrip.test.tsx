import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { schedule } from "@/test/fixtures";
import { SeasonStrip } from "./SeasonStrip";

// 1 Nov 2026 to 10 Mar 2027.
const SPAN = 129;

const strip = (overrides: Partial<typeof schedule> = {}) =>
  render(<SeasonStrip schedule={{ ...schedule, ...overrides }} cropName="Wheat" />);

describe("SeasonStrip", () => {
  it("places each window at its real date", () => {
    strip();
    const first = screen.getByTestId("season-window-1");
    expect(parseFloat(first.style.left)).toBeCloseTo((19 / SPAN) * 100, 3);
    expect(parseFloat(first.style.width)).toBeCloseTo((11 / SPAN) * 100, 3);
  });

  it("fills the season up to today", () => {
    strip();
    expect(parseFloat(screen.getByTestId("season-elapsed").style.width)).toBeCloseTo((12 / SPAN) * 100, 3);
    expect(screen.getByText("Today")).toBeInTheDocument();
    expect(screen.getByText("Day 12 after sowing")).toBeInTheDocument();
  });

  it("names the next window when none is open", () => {
    strip();
    expect(screen.getByText("Next is irrigation 1")).toBeInTheDocument();
  });

  it("names the open window", () => {
    const open = schedule.windows[0];
    strip({ days_after_sowing: 22, in_window: open, next_window: schedule.windows[1] });
    expect(screen.getByText("Irrigation 1 window is open")).toBeInTheDocument();
    expect(screen.getByTestId("season-window-1")).toHaveClass("bg-forest");
  });

  it("says when every window has passed, and stops marking today", () => {
    strip({ days_after_sowing: 200, in_window: null, next_window: null });
    expect(screen.getByText(/All listed irrigation windows have passed/)).toBeInTheDocument();
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
  });

  it("has no elapsed bar before sowing", () => {
    strip({ days_after_sowing: -5 });
    expect(screen.getByText("Sowing on 1 Nov")).toBeInTheDocument();
    expect(screen.queryByTestId("season-elapsed")).not.toBeInTheDocument();
    expect(screen.queryByText("Today")).not.toBeInTheDocument();
  });

  it("gives screen readers the windows as a list", () => {
    strip();
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Irrigation 1: 20 Nov to 30 Nov. 3 weeks after sowing.");
  });
});
