import { AlertTriangle, CheckCircle2, CircleDashed, Eye, HelpCircle, MinusCircle } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { CONFIDENCE_LABEL, RISK_LABEL, STATUS_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import type { Confidence, IrrigationStatus, RiskLevel } from "@/types/api";

const STATUS_STYLE: Record<IrrigationStatus, { icon: typeof Eye; className: string }> = {
  favorable: { icon: CheckCircle2, className: "bg-sage text-shoot-ink" },
  monitor: { icon: Eye, className: "bg-rain-wash text-rain-ink" },
  caution: { icon: AlertTriangle, className: "bg-amber-wash text-amber-ink" },
  insufficient_information: { icon: CircleDashed, className: "bg-muted text-muted-foreground" },
};

export function StatusIndicator({ status, large }: { status: IrrigationStatus; large?: boolean }) {
  const { icon: Icon, className } = STATUS_STYLE[status];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded font-medium",
        large ? "px-3 py-1.5 text-base" : "px-2 py-1 text-sm",
        className,
      )}
    >
      <Icon className={large ? "size-5" : "size-4"} aria-hidden="true" />
      {STATUS_LABEL[status]}
    </span>
  );
}

const RISK_STYLE: Record<RiskLevel, { icon: typeof Eye; className: string }> = {
  low: { icon: CheckCircle2, className: "bg-sage text-shoot-ink" },
  moderate: { icon: Eye, className: "bg-rain-wash text-rain-ink" },
  elevated: { icon: AlertTriangle, className: "bg-amber-wash text-amber-ink" },
  uncertain: { icon: HelpCircle, className: "bg-muted text-muted-foreground" },
  not_applicable: { icon: MinusCircle, className: "bg-muted text-muted-foreground" },
};

export function RiskChip({ level, prefix }: { level: RiskLevel; prefix?: string }) {
  const { icon: Icon, className } = RISK_STYLE[level];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded px-2 py-1 text-sm font-medium", className)}>
      <Icon className="size-4" aria-hidden="true" />
      {prefix ? `${prefix}: ` : ""}
      {RISK_LABEL[level]}
    </span>
  );
}

export function ConfidenceLabel({ confidence, note }: { confidence: Confidence; note?: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-sm">
      <span className="text-muted-foreground">Confidence</span>
      <span className="font-medium">{CONFIDENCE_LABEL[confidence]}</span>
      <InfoTip label="What confidence means">
        {note ? `${note} ` : ""}
        This describes how complete the inputs were. It is not a measured accuracy.
      </InfoTip>
    </span>
  );
}

/** A tap target rather than a hover tooltip, so it also works on a phone. */
export function InfoTip({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Popover>
      <PopoverTrigger
        aria-label={label}
        className="inline-flex size-6 items-center justify-center rounded text-muted-foreground hover:text-foreground"
      >
        <HelpCircle className="size-4" aria-hidden="true" />
      </PopoverTrigger>
      <PopoverContent className="w-72 text-sm">{children}</PopoverContent>
    </Popover>
  );
}
