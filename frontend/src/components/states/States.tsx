import type { ReactNode } from "react";
import { AlertTriangle, CloudOff, RotateCw, ServerCrash, Sprout, WifiOff } from "lucide-react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/services/api";
import { cn } from "@/lib/utils";

interface Direction {
  title: string;
  guidance?: string;
  scenarioLink?: boolean;
  retry?: boolean;
  icon: typeof AlertTriangle;
}

const DIRECTIONS: Record<string, Direction> = {
  weather_not_configured: {
    title: "Live weather is not connected",
    guidance:
      "This server has no OpenWeatherMap key yet, so no real weather can be shown. No substitute data is used in its place.",
    scenarioLink: true,
    retry: false,
    icon: CloudOff,
  },
  weather_auth_failed: {
    title: "The weather service rejected this server's key",
    guidance: "Check the OpenWeatherMap key on the server. New keys can take a few hours to activate.",
    scenarioLink: true,
    retry: false,
    icon: CloudOff,
  },
  weather_rate_limited: {
    title: "The weather service is limiting requests",
    guidance: "Wait a minute, then try again.",
    scenarioLink: true,
    icon: CloudOff,
  },
  weather_unavailable: {
    title: "Live weather could not be retrieved",
    guidance: "The weather service did not respond. No substitute data is shown.",
    scenarioLink: true,
    icon: CloudOff,
  },
  weather_data_invalid: {
    title: "The weather service sent unusable data",
    guidance: "It failed validation, so it is not shown. Try again in a few minutes.",
    scenarioLink: true,
    icon: CloudOff,
  },
  agent_not_configured: {
    title: "The AI assistant is not connected",
    guidance:
      "This server has no Anthropic API key yet. The Irrigation Advisor and Crop Health pages use the rule-based engine and do not need it.",
    scenarioLink: true,
    retry: false,
    icon: ServerCrash,
  },
  network_error: { title: "Can't reach FarmAgent", icon: WifiOff },
  server_unreachable: { title: "Can't reach FarmAgent", icon: WifiOff },
};

interface ErrorStateProps {
  error: unknown;
  onRetry?: () => void;
  title?: string;
  className?: string;
  compact?: boolean;
}

/** Says what failed and what to do next. Never shows a stack trace or a bare "Something went wrong". */
export function ErrorState({ error, onRetry, title, className, compact }: ErrorStateProps) {
  const code = error instanceof ApiError ? error.code : "unknown";
  const direction = DIRECTIONS[code];
  const Icon = direction?.icon ?? AlertTriangle;
  const message =
    error instanceof ApiError ? error.message : "That did not work. Try again in a moment.";
  const showRetry = Boolean(onRetry) && direction?.retry !== false;
  return (
    <div
      role="alert"
      className={cn(
        "rounded border border-clay-ink/30 bg-clay-wash text-sm",
        compact ? "p-3" : "p-5",
        className,
      )}
    >
      <div className="flex gap-3">
        <Icon className="mt-0.5 size-5 shrink-0 text-clay-ink" aria-hidden="true" />
        <div className="min-w-0 space-y-1.5">
          <p className="font-semibold text-clay-ink">{title ?? direction?.title ?? "That didn't work"}</p>
          <p>{direction?.guidance ?? message}</p>
          {(showRetry || direction?.scenarioLink) && (
            <div className="flex flex-wrap items-center gap-2 pt-1.5">
              {showRetry && (
                <Button variant="outline" size="sm" onClick={onRetry}>
                  <RotateCw aria-hidden="true" /> Try again
                </Button>
              )}
              {direction?.scenarioLink && (
                <Button variant="outline" size="sm" asChild>
                  <Link to="/scenario-lab">Open the Scenario Lab</Link>
                </Button>
              )}
            </div>
          )}
          {error instanceof ApiError && error.requestId && (
            <p className="font-mono text-[0.6875rem] text-muted-foreground">
              Reference {error.requestId}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

interface EmptyStateProps {
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  icon?: typeof Sprout;
  className?: string;
}

export function EmptyState({ title, children, action, icon: Icon = Sprout, className }: EmptyStateProps) {
  return (
    <div className={cn("rounded border border-dashed border-input p-6 text-sm sm:p-8", className)}>
      <Icon className="size-5 text-shoot-ink" aria-hidden="true" />
      <p className="display mt-3 text-base">{title}</p>
      {children && <div className="mt-1.5 max-w-prose text-muted-foreground">{children}</div>}
      {action && <div className="mt-4 flex flex-wrap gap-2">{action}</div>}
    </div>
  );
}

export function LoadingState({ label, className }: { label: string; className?: string }) {
  return (
    <div role="status" className={cn("space-y-3", className)}>
      <span className="sr-only">{label}</span>
      <div className="skeleton h-5 w-2/5" aria-hidden="true" />
      <div className="skeleton h-24 w-full" aria-hidden="true" />
    </div>
  );
}
