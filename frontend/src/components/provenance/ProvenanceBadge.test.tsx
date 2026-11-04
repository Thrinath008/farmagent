import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ProvenanceBadge } from "./ProvenanceBadge";

function label(props: React.ComponentProps<typeof ProvenanceBadge>) {
  const { container, unmount } = render(
    <TooltipProvider>
      <ProvenanceBadge {...props} />
    </TooltipProvider>,
  );
  const text = container.textContent;
  unmount();
  return text;
}

describe("ProvenanceBadge", () => {
  it("claims live only for fresh live data", () => {
    expect(label({ provenance: "live" })).toBe("Live weather");
  });

  it("marks only the fresh live state with the live dot", () => {
    const { container } = render(
      <TooltipProvider>
        <ProvenanceBadge provenance="live" />
        <ProvenanceBadge provenance="cached" />
      </TooltipProvider>,
    );
    expect(container.querySelectorAll(".live-dot")).toHaveLength(1);
    expect(screen.getByText("Live weather").querySelector(".live-dot")).not.toBeNull();
  });

  it("gives cached data its age", () => {
    expect(label({ provenance: "cached", ageSeconds: 300 })).toBe("Cached · 5 min ago");
    expect(label({ provenance: "cached" })).toBe("Cached");
  });

  it("says when real data has gone out of date", () => {
    expect(label({ provenance: "cached", isStale: true, ageSeconds: 7200 })).toBe("Out of date · 2 h ago");
    expect(label({ provenance: "live", isStale: true })).toBe("Out of date");
  });

  it("never presents simulated weather as real", () => {
    expect(label({ provenance: "simulated" })).toBe("Simulated");
    expect(label({ provenance: "simulated", historical: true })).toBe("Simulated");
    expect(label({ provenance: "simulated", isStale: true })).toBe("Simulated");
  });

  it("says when there is no weather", () => {
    expect(label({ provenance: "unavailable" })).toBe("No weather data");
    expect(label({ provenance: null })).toBe("No weather data");
    expect(label({ provenance: undefined })).toBe("No weather data");
  });

  it("does not let stored advice claim to be live now", () => {
    expect(label({ provenance: "live", historical: true })).toBe("Live at the time");
    expect(label({ provenance: "cached", historical: true })).toBe("Cached at the time");
    expect(label({ provenance: "unavailable", historical: true })).toBe("No weather data");
  });
});
