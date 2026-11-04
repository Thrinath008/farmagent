import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight, MapPin, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { Link, Navigate } from "react-router";
import { AdviceCard, SaveRecommendationButton } from "@/components/advice/AdviceCard";
import { RiskChip, StatusIndicator } from "@/components/decision/StatusIndicator";
import { Metric } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { SeasonStrip } from "@/components/SeasonStrip";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import {
  displayMeta,
  keys,
  useCurrentWeather,
  useForecast,
  useHealth,
  useRefreshFailed,
  useRefreshWeather,
  useSession,
} from "@/hooks/queries";
import {
  calendarDate,
  calendarDay,
  coordinates,
  dateTime,
  mm,
  next24Hours,
  percent,
  placeName,
  secondsSince,
  sentence,
  temp,
  windKmh,
} from "@/lib/format";
import { ONBOARDING_SKIPPED } from "@/lib/labels";
import { useFarmContext } from "@/providers/FarmProvider";
import { api, ApiError } from "@/services/api";
import type { Farm, FarmCrop, IrrigationResponse, PestRiskResponse, WeatherMeta } from "@/types/api";

function greeting(name: string | null | undefined): string {
  const hour = new Date().getHours();
  const part = hour >= 5 && hour < 12 ? "Good morning" : hour >= 12 && hour < 17 ? "Good afternoon" : "Good evening";
  return name ? `${part}, ${name}` : part;
}

function WeatherPanel({ farm }: { farm: Farm }) {
  const current = useCurrentWeather(farm.latitude, farm.longitude);
  const forecast = useForecast(farm.latitude, farm.longitude);
  const refresh = useRefreshWeather(farm.latitude, farm.longitude);
  const outlook = next24Hours(forecast.data);

  return (
    <section className="panel p-4 sm:p-5 lg:col-span-2" aria-labelledby="weather-now">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="weather-now" className="display text-base">
          Weather now
        </h2>
        {current.data && (
          <div className="flex items-center gap-1">
            <ProvenanceBadge
              {...badgeProps(displayMeta(current.data.meta, current.isRefetchError || refresh.isError))}
            />
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="Refresh weather"
              onClick={() => refresh.mutate()}
              disabled={refresh.isPending}
            >
              <RefreshCw className={refresh.isPending ? "animate-spin" : ""} aria-hidden="true" />
            </Button>
          </div>
        )}
      </div>

      {current.isPending && <LoadingState label="Loading current weather" className="mt-4" />}
      {current.isError && !current.data && (
        <ErrorState className="mt-4" error={current.error} onRetry={() => current.refetch()} />
      )}
      {current.data && (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <Metric
              large
              label="Temperature"
              value={temp(current.data.temperature_c)}
              note={sentence(current.data.description)}
            />
            <Metric label="Humidity" value={percent(current.data.humidity_pct)} />
            <Metric
              label="Chance of rain, next 24 h"
              value={percent(outlook.chance)}
              note={outlook.rain !== null ? `${mm(outlook.rain)} expected` : "Forecast unavailable"}
            />
            <Metric label="Wind" value={windKmh(current.data.wind_speed_ms)} />
          </dl>
          {current.data.meta.warning && (
            <p className="mt-3 rounded bg-amber-wash p-2.5 text-sm text-amber-ink">
              {current.data.meta.warning}
            </p>
          )}
          {refresh.isError && (
            <p className="mt-3 rounded bg-amber-wash p-2.5 text-sm text-amber-ink" role="alert">
              The refresh failed, so the figures above may be out of date.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function badgeProps(meta: WeatherMeta) {
  return {
    provenance: meta.provenance,
    isStale: meta.is_stale,
    ageSeconds: meta.age_seconds,
    source: meta.source,
  };
}

/** An assessment is only as current as the weather behind it, so it carries that weather's label. */
function assessmentBadgeProps(data: IrrigationResponse | PestRiskResponse) {
  return {
    provenance: data.assessment.weather_provenance,
    isStale: data.weather?.is_stale,
    ageSeconds: secondsSince(data.weather?.observed_at),
    source: data.weather?.source,
  };
}

function IrrigationPanel({ farm, crop }: { farm: Farm; crop: FarmCrop }) {
  const query = useQuery({
    queryKey: ["overview-irrigation", farm.id, crop.id, crop.growth_stage, farm.updated_at],
    queryFn: () =>
      api.assessIrrigation({ farm_id: farm.id, farm_crop_id: crop.id, crop: crop.crop }),
    staleTime: 60_000,
    refetchInterval: 10 * 60_000,
  });
  return (
    <section className="panel flex flex-col p-4 sm:p-5" aria-labelledby="irrigation-status">
      <h2 id="irrigation-status" className="display text-base">
        Irrigation status
      </h2>
      {query.isPending && <LoadingState label="Assessing irrigation" className="mt-4" />}
      {query.isError && <ErrorState compact className="mt-3" error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="mt-3 flex flex-1 flex-col items-start gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <StatusIndicator status={query.data.assessment.status} />
            <ProvenanceBadge {...assessmentBadgeProps(query.data)} />
          </div>
          <p className="text-sm">{query.data.assessment.headline}</p>
          <Button variant="link" className="mt-auto h-auto p-0" asChild>
            <Link to="/irrigation">
              Open the Irrigation Advisor <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        </div>
      )}
    </section>
  );
}

function RiskPanel({ farm, crop }: { farm: Farm; crop: FarmCrop }) {
  const query = useQuery({
    queryKey: ["overview-risk", farm.id, crop.id, crop.growth_stage, farm.updated_at],
    queryFn: () => api.assessPestRisk({ farm_id: farm.id, farm_crop_id: crop.id, crop: crop.crop }),
    staleTime: 60_000,
    refetchInterval: 10 * 60_000,
  });
  return (
    <section className="panel flex flex-col p-4 sm:p-5" aria-labelledby="crop-risk">
      <h2 id="crop-risk" className="display text-base">
        Weather-related crop risk
      </h2>
      {query.isPending && <LoadingState label="Assessing crop risk" className="mt-4" />}
      {query.isError && <ErrorState compact className="mt-3" error={query.error} onRetry={() => query.refetch()} />}
      {query.data && (
        <div className="mt-3 flex flex-1 flex-col items-start gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <RiskChip level={query.data.assessment.overall_classification} />
            <ProvenanceBadge {...assessmentBadgeProps(query.data)} />
          </div>
          <p className="text-sm">{query.data.assessment.headline}</p>
          <p className="text-xs text-muted-foreground">Based on weather. It is not a diagnosis.</p>
          <Button variant="link" className="mt-auto h-auto p-0" asChild>
            <Link to="/crop-health">
              Open Crop Health & Risk <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        </div>
      )}
    </section>
  );
}

function FiveDays({ farm }: { farm: Farm }) {
  const forecast = useForecast(farm.latitude, farm.longitude);
  const refreshFailed = useRefreshFailed(farm.latitude, farm.longitude);
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="five-days">
      <div className="flex items-center justify-between gap-2">
        <h2 id="five-days" className="display text-base">
          Forecast
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {forecast.data && (
            <ProvenanceBadge
              {...badgeProps(displayMeta(forecast.data.meta, forecast.isRefetchError || refreshFailed))}
            />
          )}
          <Button variant="link" className="h-auto p-0" asChild>
            <Link to="/weather">
              Weather Intelligence <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </div>
      {forecast.isPending && <LoadingState label="Loading the forecast" className="mt-4" />}
      {forecast.isError && !forecast.data && (
        <ErrorState className="mt-4" compact error={forecast.error} onRetry={() => forecast.refetch()} />
      )}
      {forecast.data && (
        <ul className="-mx-4 mt-3 flex overflow-x-auto px-4 sm:mx-0 sm:grid sm:grid-cols-[repeat(auto-fit,minmax(7.5rem,1fr))] sm:px-0">
          {forecast.data.daily.slice(0, 6).map((day) => (
            <li
              key={day.date}
              className="min-w-[7.5rem] border-l border-border pr-3 pl-3 first:border-l-0 first:pl-0"
            >
              <p className="font-mono text-xs text-muted-foreground">{calendarDay(day.date)}</p>
              <p className="numeral mt-2 text-xl">{temp(day.temp_max_c)}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">Low {temp(day.temp_min_c)}</p>
              <p className="mt-2 text-sm">{mm(day.rain_total_mm)}</p>
              <p className="text-xs text-muted-foreground">{percent(day.rain_probability_max_pct)} chance of rain</p>
              {day.periods < 8 && <p className="mt-1 text-xs text-muted-foreground">Part of the day</p>}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Briefing({ farm, crop }: { farm: Farm; crop: FarmCrop | null }) {
  const health = useHealth();
  const briefing = useMutation({
    mutationFn: () => api.analyzeFarm({ farm_id: farm.id, farm_crop_id: crop?.id ?? null }),
    onError: (error) => {
      if (!(error instanceof ApiError)) toast.error("The briefing could not be prepared.");
    },
  });
  const configured = health.data?.ai_configured;
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="ai-briefing">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="ai-briefing" className="display text-base">
          AI farm briefing
        </h2>
        {configured && (
          <Button size="sm" onClick={() => briefing.mutate()} disabled={briefing.isPending}>
            <Sparkles aria-hidden="true" />
            {briefing.isPending ? "Preparing, this can take a minute…" : briefing.data ? "Prepare again" : "Prepare a briefing"}
          </Button>
        )}
      </div>
      {health.data && !configured && (
        <p className="mt-2 text-sm text-muted-foreground">
          The AI assistant is not connected on this server, so briefings are unavailable. The status
          panels above come from the rule-based engine and still work.
        </p>
      )}
      {configured && !briefing.data && !briefing.isPending && !briefing.isError && (
        <p className="mt-2 text-sm text-muted-foreground">
          Claude checks the weather and your crop, then summarises what matters for this farm today.
        </p>
      )}
      {briefing.isPending && <LoadingState label="Preparing the briefing" className="mt-4" />}
      {briefing.isError && <ErrorState className="mt-3" compact error={briefing.error} onRetry={() => briefing.mutate()} />}
      {briefing.data && (
        <AdviceCard
          className="mt-3 border-none bg-transparent !p-0"
          advice={briefing.data.advice}
          footer={
            <SaveRecommendationButton
              input={{
                advice: briefing.data.advice,
                origin: "assistant",
                farm_id: farm.id,
                crop: crop?.crop ?? null,
                latitude: farm.latitude,
                longitude: farm.longitude,
              }}
            />
          }
        />
      )}
    </section>
  );
}

function RecentRecommendations({ farm }: { farm: Farm }) {
  const query = useQuery({
    queryKey: [...keys.recommendations, "recent", farm.id],
    queryFn: () => api.recommendations({ limit: 4, farm_id: farm.id }),
  });
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="recent-recommendations">
      <div className="flex items-center justify-between gap-2">
        <h2 id="recent-recommendations" className="display text-base">
          Recent recommendations
        </h2>
        <Button variant="link" className="h-auto p-0" asChild>
          <Link to="/history">
            Farming History <ArrowRight aria-hidden="true" />
          </Link>
        </Button>
      </div>
      {query.isPending && <LoadingState label="Loading recommendations" className="mt-4" />}
      {query.isError && <ErrorState className="mt-3" compact error={query.error} onRetry={() => query.refetch()} />}
      {query.data?.length === 0 && (
        <p className="mt-2 text-sm text-muted-foreground">
          Nothing saved for this farm yet. Save advice from the Irrigation Advisor or the assistant
          and it will appear here.
        </p>
      )}
      {query.data && query.data.length > 0 && (
        <ul className="mt-2 divide-y divide-border">
          {query.data.map((item) => (
            <li key={item.id} className="py-2.5 text-sm">
              <p className="font-medium">{item.recommendation ?? item.summary}</p>
              <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span className="font-mono">{dateTime(item.created_at)}</span>
                {item.weather_provenance && (
                  <ProvenanceBadge provenance={item.weather_provenance} historical className="!py-0.5" />
                )}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function OverviewPage() {
  const session = useSession();
  const { farms, farm, crop, isLoading, error, refetch } = useFarmContext();

  if (isLoading) return <LoadingState label="Loading your farm" />;
  if (error && farms.length === 0) return <ErrorState error={error} onRetry={refetch} />;

  const skipped = localStorage.getItem(ONBOARDING_SKIPPED) === "1";
  if (!farm) {
    if (!skipped) return <Navigate to="/welcome" replace />;
    return (
      <div className="space-y-5">
        <h1 className="display text-2xl sm:text-3xl">{greeting(session.data?.display_name)}</h1>
        <EmptyState
          title="Add your farm to see advice for your own fields"
          action={
            <>
              <Button asChild>
                <Link to="/welcome">Set up your farm</Link>
              </Button>
              <Button variant="outline" asChild>
                <Link to="/scenario-lab">Try the Scenario Lab</Link>
              </Button>
            </>
          }
        >
          FarmAgent needs a location and a crop before it can assess irrigation or weather risk.
        </EmptyState>
      </div>
    );
  }

  const place = placeName(farm);
  const hasLocation = farm.latitude !== null && farm.longitude !== null;

  return (
    <div className="space-y-5">
      <header>
        <h1 className="display text-2xl sm:text-3xl">{greeting(session.data?.display_name)}</h1>
        <p className="mt-1.5 flex flex-wrap items-center gap-x-2 text-[0.9375rem] text-muted-foreground">
          <MapPin className="size-4 text-shoot-ink" aria-hidden="true" />
          <span className="font-medium text-foreground">{farm.name ?? "Your farm"}</span>
          {place && <span>· {place}</span>}
          {!place && hasLocation && (
            <span className="font-mono text-xs">· {coordinates(farm.latitude as number, farm.longitude as number)}</span>
          )}
          {crop && (
            <span>
              · {crop.crop_name}
              {crop.growth_stage_label ? `, ${crop.growth_stage_label.toLowerCase()}` : ""}
            </span>
          )}
        </p>
      </header>

      {crop?.irrigation_schedule && (
        <section className="panel p-4 sm:p-5">
          <SeasonStrip schedule={crop.irrigation_schedule} cropName={crop.crop_name} />
        </section>
      )}
      {crop && !crop.irrigation_schedule && crop.support_level === "rules_implemented" && (
        <EmptyState
          title={
            crop.sowing_date
              ? "The published timetable does not cover this sowing date"
              : "Add a sowing date to see your irrigation season"
          }
          action={
            <Button variant="outline" size="sm" asChild>
              <Link to="/farm">{crop.sowing_date ? "Check it in My Farm" : "Add it in My Farm"}</Link>
            </Button>
          }
        >
          {crop.sowing_date
            ? `The timetable FarmAgent uses covers ${crop.crop_name.toLowerCase()} sown between October and mid-December. For ${calendarDate(crop.sowing_date, { year: "numeric" })}, no irrigation dates are shown, and weather checks still work.`
            : `With a sowing date, FarmAgent can lay out the published irrigation windows for ${crop.crop_name.toLowerCase()} at their real dates.`}
        </EmptyState>
      )}
      {!crop && (
        <EmptyState
          title="Add a crop to this farm"
          action={
            <Button variant="outline" size="sm" asChild>
              <Link to="/farm">Add a crop</Link>
            </Button>
          }
        >
          Irrigation and crop risk assessments are made for a specific crop.
        </EmptyState>
      )}

      {!hasLocation ? (
        <EmptyState
          title="Set this farm's location to get weather"
          action={
            <Button variant="outline" size="sm" asChild>
              <Link to="/farm">Set the location</Link>
            </Button>
          }
        >
          Weather is looked up by location, and FarmAgent will not guess where your farm is.
        </EmptyState>
      ) : (
        <>
          <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
            <WeatherPanel farm={farm} />
            {crop && <IrrigationPanel farm={farm} crop={crop} />}
            {crop && <RiskPanel farm={farm} crop={crop} />}
          </div>
          <FiveDays farm={farm} />
        </>
      )}

      <div className="grid items-start gap-5 lg:grid-cols-2">
        <Briefing farm={farm} crop={crop} />
        <RecentRecommendations farm={farm} />
      </div>
    </div>
  );
}
