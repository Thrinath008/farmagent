import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BadgeCheck, Bookmark, BookmarkCheck, CircleUserRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ConfidenceLabel, RiskChip } from "@/components/decision/StatusIndicator";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { dateTime, mm, percent, secondsSince, sentence, temp, windKmh } from "@/lib/format";
import { keys } from "@/hooks/queries";
import { GENERATED_BY_LABEL, INTENT_LABEL } from "@/lib/labels";
import { api, ApiError } from "@/services/api";
import type { FarmingAdvice, RecommendationInput, WeatherContext } from "@/types/api";
import { cn } from "@/lib/utils";

export function WeatherContextCard({
  context,
  historical,
}: {
  context: WeatherContext;
  historical?: boolean;
}) {
  const rows: [string, string][] = [
    ["Temperature", temp(context.temperature_c)],
    ["Humidity", percent(context.humidity_pct)],
    [`Chance of rain, next ${context.window_hours} h`, percent(context.rain_probability_pct)],
    [`Expected rain, next ${context.window_hours} h`, mm(context.expected_rain_mm)],
    ["Wind", windKmh(context.wind_speed_ms)],
  ];
  return (
    <div className="rounded border border-border bg-muted/50 p-3" data-testid="weather-context">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">
          Weather used{context.location_name ? ` · ${context.location_name}` : ""}
        </p>
        <ProvenanceBadge
          provenance={context.provenance}
          isStale={context.is_stale}
          ageSeconds={secondsSince(context.observed_at)}
          source={context.source}
          historical={historical}
        />
      </div>
      <dl className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="text-sm font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-xs text-muted-foreground">
        {context.description ? `${sentence(context.description)}. ` : ""}
        Source: {context.source}
        {context.observed_at ? `, observed ${dateTime(context.observed_at)}` : ""}.
      </p>
    </div>
  );
}

function Items({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div>
      <h4 className="text-sm font-medium">{title}</h4>
      <ul className="mt-1 list-disc space-y-1 pl-5 text-sm text-foreground/90 marker:text-muted-foreground">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

export function SaveRecommendationButton({
  input,
  alreadySaved,
}: {
  input: RecommendationInput;
  alreadySaved?: boolean;
}) {
  const client = useQueryClient();
  const [saved, setSaved] = useState(Boolean(alreadySaved));
  const mutation = useMutation({
    mutationFn: () => api.saveRecommendation(input),
    onSuccess: () => {
      setSaved(true);
      toast.success("Saved to Farming History");
      client.invalidateQueries({ queryKey: keys.recommendations });
    },
    onError: (error) =>
      toast.error(error instanceof ApiError ? error.message : "This could not be saved. Try again."),
  });
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={saved || mutation.isPending}
      onClick={() => mutation.mutate()}
    >
      {saved ? <BookmarkCheck aria-hidden="true" /> : <Bookmark aria-hidden="true" />}
      {saved ? "Saved to history" : mutation.isPending ? "Saving…" : "Save to history"}
    </Button>
  );
}

/** The one presentation of a recommendation, used by the assistant, the briefing and history. */
export function AdviceCard({
  advice,
  footer,
  historical,
  className,
}: {
  advice: FarmingAdvice;
  footer?: React.ReactNode;
  /** A stored answer being read later. Its weather is a record of then, not a reading of now. */
  historical?: boolean;
  className?: string;
}) {
  const hasJudgement = advice.risk_level !== "not_applicable" || advice.confidence !== "not_applicable";
  return (
    <article className={cn("panel p-4 sm:p-5", className)} data-testid="advice-card">
      <p className="eyebrow">{INTENT_LABEL[advice.intent] ?? "Advice"}</p>
      {advice.recommendation && (
        <p className="display mt-2 text-lg sm:text-xl">{advice.recommendation}</p>
      )}
      <p className={cn("text-[0.9375rem] leading-relaxed", advice.recommendation ? "mt-2" : "mt-1.5")}>
        {advice.summary}
      </p>

      {hasJudgement && (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2">
          {advice.risk_level !== "not_applicable" && <RiskChip level={advice.risk_level} prefix="Risk" />}
          {advice.confidence !== "not_applicable" && <ConfidenceLabel confidence={advice.confidence} />}
        </div>
      )}

      {advice.weather_context && (
        <div className="mt-4">
          <WeatherContextCard context={advice.weather_context} historical={historical} />
        </div>
      )}

      <div className="mt-4 space-y-3">
        <Items title="Why" items={advice.reasoning} />
        <Items title="What to do next" items={advice.next_steps} />
        <Items title="What is still unknown" items={advice.missing_information} />
      </div>

      {advice.requires_expert_verification && (
        <p className="mt-4 flex gap-2 rounded bg-amber-wash p-3 text-sm text-amber-ink">
          <CircleUserRound className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          Check this with your agricultural extension officer or Krishi Vigyan Kendra before acting.
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
        <div className="min-w-0 text-xs text-muted-foreground">
          <p className="flex items-center gap-1.5">
            <BadgeCheck className="size-3.5" aria-hidden="true" />
            {GENERATED_BY_LABEL[advice.generated_by] ?? advice.generated_by}
          </p>
          {advice.data_sources.length > 0 && (
            <p className="mt-1">Sources: {advice.data_sources.join(" · ")}</p>
          )}
        </div>
        {footer}
      </div>
    </article>
  );
}
