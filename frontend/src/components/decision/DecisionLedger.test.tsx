import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { factors } from "@/test/fixtures";
import { DecisionLedger } from "./DecisionLedger";

function ledger(score = -1) {
  render(
    <TooltipProvider>
      <DecisionLedger factors={factors} score={score} />
    </TooltipProvider>,
  );
}

const blocks = (key: string) => {
  const row = within(screen.getByTestId(`factor-${key}`));
  return {
    against: row.getByTestId("against-blocks").children.length,
    supports: row.getByTestId("supports-blocks").children.length,
    row,
  };
};

describe("DecisionLedger", () => {
  it("shows the score as a signed tally", () => {
    ledger(-1);
    expect(screen.getByTestId("ledger-score")).toHaveTextContent("−1");
  });

  it("draws one block per rule point, on the side the factor argues for", () => {
    ledger();
    expect(blocks("forecast_rain")).toMatchObject({ against: 2, supports: 0 });
    expect(blocks("heat")).toMatchObject({ against: 0, supports: 1 });
    expect(blocks("wind")).toMatchObject({ against: 0, supports: 0 });
  });

  it("marks an unknown factor without counting it either way", () => {
    ledger();
    const { against, supports, row } = blocks("soil_moisture");
    expect(against).toBe(0);
    expect(supports).toBe(1);
    expect(row.getByTestId("supports-blocks").firstElementChild).toHaveClass("border-dashed");
    expect(row.getByText("Not known, so it counts neither way.")).toBeInTheDocument();
  });

  it("says each factor's weight in words, so colour is not the only signal", () => {
    ledger();
    expect(blocks("forecast_rain").row.getByText("2 points against irrigating.")).toBeInTheDocument();
    expect(blocks("heat").row.getByText("1 point for irrigating.")).toBeInTheDocument();
    expect(blocks("wind").row.getByText("Counts neither way.")).toBeInTheDocument();
  });
});
