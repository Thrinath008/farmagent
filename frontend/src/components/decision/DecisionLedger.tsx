import { motion } from "framer-motion";
import { signed } from "@/lib/format";
import type { DecisionFactor } from "@/types/api";
import { InfoTip } from "./StatusIndicator";

const MIN_UNITS = 3;

/** One block per rule point, so the bar shows a tally of rule weights and not a measurement. */
export function WeightBlocks({
  weight,
  units,
  unknown,
}: {
  weight: number;
  units: number;
  unknown?: boolean;
}) {
  const against = Array.from({ length: Math.max(-weight, 0) });
  const supports = Array.from({ length: Math.max(weight, 0) });
  return (
    <div
      className="grid grid-cols-[1fr_1px_1fr] items-center gap-1"
      style={{ width: `${(units * 2 + 1) * 1.05}rem`, maxWidth: "100%" }}
    >
      <div className="flex justify-end gap-0.5" data-testid="against-blocks">
        {against.map((_, index) => (
          <motion.span
            key={index}
            className="h-3.5 w-3.5 rounded-[1px] bg-rain-mark"
            initial={{ opacity: 0, x: 6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.18, delay: index * 0.04 }}
          />
        ))}
      </div>
      <span className="h-6 w-px bg-ink/50" aria-hidden="true" />
      <div className="flex gap-0.5" data-testid="supports-blocks">
        {unknown && (
          <span className="h-3.5 w-3.5 rounded-[1px] border border-dashed border-muted-foreground" />
        )}
        {supports.map((_, index) => (
          <motion.span
            key={index}
            className="h-3.5 w-3.5 rounded-[1px] bg-shoot"
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.18, delay: index * 0.04 }}
          />
        ))}
      </div>
    </div>
  );
}

function directionWords(factor: DecisionFactor): string {
  if (factor.direction === "unknown") return "Not known, so it counts neither way.";
  if (factor.direction === "neutral" || factor.weight === 0) return "Counts neither way.";
  const points = Math.abs(factor.weight);
  const side = factor.weight > 0 ? "for irrigating" : "against irrigating";
  return `${points} ${points === 1 ? "point" : "points"} ${side}.`;
}

/**
 * How the decision was reached: every factor the engine weighed, on one line, left against irrigating
 * and right in favour. This is the page's main argument, so it stays readable as a list without
 * colour or motion.
 */
export function DecisionLedger({
  factors,
  score,
  className,
}: {
  factors: DecisionFactor[];
  score: number;
  className?: string;
}) {
  const units = Math.max(MIN_UNITS, ...factors.map((factor) => Math.abs(factor.weight)));
  return (
    <div className={className}>
      <div className="flex items-center justify-between gap-3">
        <h3 className="display text-base">How this was decided</h3>
        <span className="inline-flex items-center gap-1 text-sm">
          <span className="text-muted-foreground">Rule score</span>
          <span className="numeral text-lg" data-testid="ledger-score">
            {signed(score)}
          </span>
          <InfoTip label="What the rule score means">
            A tally of the rule weights below. It is not a probability or a measurement, and the rules
            have not been calibrated in field trials.
          </InfoTip>
        </span>
      </div>
      <div className="mt-2 flex items-center gap-4 text-xs text-muted-foreground" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[1px] bg-rain-mark" /> Against irrigating
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[1px] bg-shoot" /> Supports irrigating
        </span>
      </div>
      <ul className="mt-3 divide-y divide-border border-y border-border">
        {factors.map((factor) => (
          <li
            key={factor.key}
            className="grid gap-x-5 gap-y-2 py-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-start"
            data-testid={`factor-${factor.key}`}
          >
            <div className="min-w-0">
              <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
                <span className="font-medium">{factor.label}</span>
                <span className="font-mono text-xs text-muted-foreground">{factor.value}</span>
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{factor.explanation}</p>
              <p className="sr-only">{directionWords(factor)}</p>
            </div>
            <WeightBlocks
              weight={factor.weight}
              units={units}
              unknown={factor.direction === "unknown"}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}
