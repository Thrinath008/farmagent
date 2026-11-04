import { useState } from "react";
import { MapPin, RefreshCw } from "lucide-react";
import { ForecastCharts } from "@/components/charts/ForecastCharts";
import { LocationPicker, type PickedPlace } from "@/components/forms/LocationPicker";
import { Metric, PageHeader } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { displayMeta, useCurrentWeather, useForecast, useRefreshWeather } from "@/hooks/queries";
import {
  calendarDay,
  coordinates,
  mm,
  next24Hours,
  percent,
  placeDayTime,
  placeTitle,
  placeTime,
  sentence,
  temp,
  windKmh,
} from "@/lib/format";
import { cn } from "@/lib/utils";
import { useFarmContext } from "@/providers/FarmProvider";
import type { Forecast } from "@/types/api";

function ForecastTable({ forecast, view }: { forecast: Forecast; view: "hourly" | "daily" }) {
  return (
    <details className="mt-5 text-sm">
      <summary className="cursor-pointer font-medium text-shoot-ink">Show every value as a table</summary>
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b border-border">
              <th scope="col" className="py-2 pr-4 font-medium">
                {view === "hourly" ? "Time at this location" : "Day"}
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">
                {view === "hourly" ? "Temperature" : "High / low"}
              </th>
              <th scope="col" className="py-2 pr-4 font-medium">Expected rain</th>
              <th scope="col" className="py-2 pr-4 font-medium">Chance of rain</th>
              <th scope="col" className="py-2 font-medium">Conditions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {view === "hourly"
              ? forecast.hourly.map((point) => (
                  <tr key={point.time}>
                    <th scope="row" className="py-1.5 pr-4 font-mono text-xs font-normal">
                      {placeDayTime(point.time, forecast.timezone_offset_seconds)}
                    </th>
                    <td className="py-1.5 pr-4">{temp(point.temperature_c)}</td>
                    <td className="py-1.5 pr-4">{mm(point.rain_mm)}</td>
                    <td className="py-1.5 pr-4">{percent(point.rain_probability_pct)}</td>
                    <td className="py-1.5">{sentence(point.description)}</td>
                  </tr>
                ))
              : forecast.daily.map((day) => (
                  <tr key={day.date}>
                    <th scope="row" className="py-1.5 pr-4 font-mono text-xs font-normal">
                      {calendarDay(day.date)}
                      {day.periods < 8 ? " (part of the day)" : ""}
                    </th>
                    <td className="py-1.5 pr-4">
                      {temp(day.temp_max_c)} / {temp(day.temp_min_c)}
                    </td>
                    <td className="py-1.5 pr-4">{mm(day.rain_total_mm)}</td>
                    <td className="py-1.5 pr-4">{percent(day.rain_probability_max_pct)}</td>
                    <td className="py-1.5">{sentence(day.description)}</td>
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
    </details>
  );
}

export function WeatherPage() {
  const { farm, isLoading } = useFarmContext();
  const [picked, setPicked] = useState<PickedPlace | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [view, setView] = useState<"hourly" | "daily">("hourly");

  const lat = picked?.latitude ?? farm?.latitude ?? null;
  const lon = picked?.longitude ?? farm?.longitude ?? null;
  const current = useCurrentWeather(lat, lon);
  const forecast = useForecast(lat, lon);
  const refresh = useRefreshWeather(lat, lon);
  const hasPlace = lat !== null && lon !== null;

  const title = picked
    ? placeTitle(picked)
    : (current.data?.location_name ?? farm?.location_name ?? farm?.name ?? null);
  const meta = current.data
    ? displayMeta(current.data.meta, current.isRefetchError || refresh.isError)
    : null;
  const outlook = next24Hours(forecast.data);

  function pick(place: PickedPlace) {
    setPicked(place);
    setChoosing(false);
    refresh.reset();
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Weather Intelligence"
        description="Current conditions and a five-day forecast from OpenWeatherMap. Every figure is labelled with where it came from."
        actions={
          hasPlace && (
            <Button variant="outline" onClick={() => refresh.mutate()} disabled={refresh.isPending}>
              <RefreshCw className={refresh.isPending ? "animate-spin" : ""} aria-hidden="true" />
              {refresh.isPending ? "Refreshing…" : "Refresh weather"}
            </Button>
          )
        }
      />

      <section className="panel p-4 sm:p-5" aria-label="Location">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="flex min-w-0 items-center gap-2 text-sm">
            <MapPin className="size-4 shrink-0 text-shoot-ink" aria-hidden="true" />
            {hasPlace ? (
              <span>
                <span className="font-medium">{title ?? "Selected location"}</span>{" "}
                <span className="font-mono text-xs text-muted-foreground">
                  {coordinates(lat as number, lon as number)}
                </span>
              </span>
            ) : (
              <span className="text-muted-foreground">No location chosen yet</span>
            )}
          </p>
          <div className="flex gap-2">
            {picked && farm?.latitude != null && (
              <Button variant="ghost" size="sm" onClick={() => setPicked(null)}>
                Back to {farm.name ?? "my farm"}
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              aria-expanded={choosing || (!hasPlace && !isLoading)}
              onClick={() => setChoosing((open) => !open)}
              disabled={!hasPlace}
            >
              Change location
            </Button>
          </div>
        </div>
        {(choosing || (!hasPlace && !isLoading)) && (
          <div className="mt-4 border-t border-border pt-4">
            <LocationPicker idPrefix="weather-location" onPick={pick} />
          </div>
        )}
      </section>

      {!hasPlace && !isLoading && (
        <EmptyState title="Choose a location to see its weather">
          Search above, use your device's location, or enter coordinates.
        </EmptyState>
      )}

      {hasPlace && (
        <section className="panel p-4 sm:p-5" aria-labelledby="current-heading">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="current-heading" className="display text-lg">
              Now
            </h2>
            {meta && (
              <ProvenanceBadge
                provenance={meta.provenance}
                isStale={meta.is_stale}
                ageSeconds={meta.age_seconds}
                source={meta.source}
              />
            )}
          </div>
          {current.isPending && <LoadingState label="Loading current weather" className="mt-4" />}
          {current.isError && !current.data && (
            <ErrorState className="mt-4" error={current.error} onRetry={() => current.refetch()} />
          )}
          {current.data && meta && (
            <>
              <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-5 sm:grid-cols-3 lg:grid-cols-6">
                <Metric
                  large
                  label="Temperature"
                  value={temp(current.data.temperature_c)}
                  note={sentence(current.data.description)}
                />
                <Metric label="Feels like" value={temp(current.data.feels_like_c)} />
                <Metric label="Humidity" value={percent(current.data.humidity_pct)} />
                <Metric
                  label="Wind"
                  value={windKmh(current.data.wind_speed_ms)}
                  note={
                    current.data.wind_gust_ms !== null
                      ? `Gusts ${windKmh(current.data.wind_gust_ms)}`
                      : undefined
                  }
                />
                <Metric
                  label="Rain in the last hour"
                  value={current.data.rain_last_1h_mm !== null ? mm(current.data.rain_last_1h_mm) : "None"}
                  note={current.data.rain_last_1h_mm === null ? "As reported by the provider" : undefined}
                />
                <Metric
                  label="Chance of rain, next 24 h"
                  value={percent(outlook.chance)}
                  note={outlook.rain !== null ? `${mm(outlook.rain)} expected` : undefined}
                />
              </dl>
              <p className="mt-4 text-xs text-muted-foreground" data-testid="last-updated">
                Observed at {placeTime(current.data.observed_at, current.data.timezone_offset_seconds)} location time.
                {meta.fetched_at &&
                  ` Retrieved at ${placeTime(meta.fetched_at, current.data.timezone_offset_seconds)}.`}{" "}
                Source: {meta.source}.
              </p>
              {meta.warning && (
                <p className="mt-3 rounded bg-amber-wash p-2.5 text-sm text-amber-ink" role="status">
                  {meta.warning}
                </p>
              )}
            </>
          )}
        </section>
      )}

      {refresh.isError && <ErrorState compact title="The refresh failed" error={refresh.error} onRetry={() => refresh.mutate()} />}

      {hasPlace && (
        <section className="panel p-4 sm:p-5" aria-labelledby="forecast-heading">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 id="forecast-heading" className="display text-lg">
              Forecast
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              {forecast.data && (
                <ProvenanceBadge
                  provenance={displayMeta(forecast.data.meta, forecast.isRefetchError || refresh.isError).provenance}
                  isStale={displayMeta(forecast.data.meta, forecast.isRefetchError || refresh.isError).is_stale}
                  ageSeconds={forecast.data.meta.age_seconds}
                  source={forecast.data.meta.source}
                />
              )}
              <div role="group" aria-label="Forecast view" className="flex rounded border border-input p-0.5">
                {(
                  [
                    ["hourly", "Every 3 hours"],
                    ["daily", "By day"],
                  ] as const
                ).map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    aria-pressed={view === value}
                    onClick={() => setView(value)}
                    className={cn(
                      "rounded-[2px] px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
                      view === value ? "bg-primary text-primary-foreground" : "hover:bg-muted",
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          </div>
          {forecast.isPending && <LoadingState label="Loading the forecast" className="mt-4" />}
          {forecast.isError && !forecast.data && (
            <ErrorState className="mt-4" error={forecast.error} onRetry={() => forecast.refetch()} />
          )}
          {forecast.data && (
            <div className="mt-5">
              <ForecastCharts forecast={forecast.data} view={view} />
              <ForecastTable forecast={forecast.data} view={view} />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
