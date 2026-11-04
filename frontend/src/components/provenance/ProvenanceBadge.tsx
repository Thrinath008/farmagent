import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { age } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { DataProvenance } from "@/types/api";

interface ProvenanceBadgeProps {
  provenance: DataProvenance | null | undefined;
  isStale?: boolean;
  ageSeconds?: number | null;
  source?: string | null;
  /** The weather belongs to a stored record, so it describes then, not now. */
  historical?: boolean;
  className?: string;
}

interface Stamp {
  label: string;
  explanation: string;
  className: string;
  live?: boolean;
}

function describe({ provenance, isStale, ageSeconds, source, historical }: ProvenanceBadgeProps): Stamp {
  const from = source ? ` from ${source}` : "";
  if (historical && (provenance === "live" || provenance === "cached")) {
    return {
      label: provenance === "live" ? "Live at the time" : "Cached at the time",
      explanation: `Real weather${from} when this advice was given. Conditions will have changed since, so reassess before acting on it.`,
      className: "text-muted-foreground",
    };
  }
  if (provenance === "simulated") {
    return {
      label: "Simulated",
      explanation: "Made-up weather for demonstration. It is not real and must not guide field work.",
      className: "stamp-simulated",
    };
  }
  if (provenance === "live" && !isStale) {
    return {
      label: "Live weather",
      explanation: `Retrieved${from} just now, in response to this request.`,
      className: "text-shoot-ink",
      live: true,
    };
  }
  if (provenance === "live" || (provenance === "cached" && isStale)) {
    return {
      label: `Out of date${ageSeconds != null ? ` · ${age(ageSeconds)}` : ""}`,
      explanation: `Real weather${from}, but old enough that conditions may have changed. Refresh before you rely on it.`,
      className: "text-amber-ink bg-amber-wash",
    };
  }
  if (provenance === "cached") {
    return {
      label: `Cached${ageSeconds != null ? ` · ${age(ageSeconds)}` : ""}`,
      explanation: `Real weather${from}, saved from a recent request rather than fetched just now.`,
      className: "text-rain-ink",
    };
  }
  return {
    label: "No weather data",
    explanation: "Verified weather could not be retrieved, so none is shown.",
    className: "text-clay-ink bg-clay-wash",
  };
}

/** Says where weather came from. Every weather value on screen sits next to one of these. */
export function ProvenanceBadge(props: ProvenanceBadgeProps) {
  const stamp = describe(props);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className={cn("stamp cursor-help", stamp.className, props.className)}>
          {stamp.live && <span className="live-dot" aria-hidden="true" />}
          {stamp.label}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-64">{stamp.explanation}</TooltipContent>
    </Tooltip>
  );
}
