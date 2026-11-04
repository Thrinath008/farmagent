import type { ReactNode } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { calendarDay, mm, percent, placeDayTime, temp } from "@/lib/format";
import type { Forecast } from "@/types/api";

const COLOR = {
  warm: "#b4740e",
  cool: "#1f77a8",
  rain: "#1f77a8",
  grid: "#e4eadd",
  axis: "#5a665e",
  surface: "#fdfdf9",
};

const X_AXIS_PROPS = { dataKey: "label", scale: "band" as const };

const AXIS_PROPS = {
  tick: { fill: COLOR.axis, fontSize: 11, fontFamily: "IBM Plex Mono, monospace" },
  tickLine: false,
  axisLine: false,
};

interface Row {
  label: string;
  temperature?: number;
  high?: number;
  low?: number;
  rain: number;
  chance: number;
}

function rows(forecast: Forecast, view: "hourly" | "daily"): Row[] {
  if (view === "daily") {
    return forecast.daily.map((day) => ({
      label: calendarDay(day.date),
      high: day.temp_max_c,
      low: day.temp_min_c,
      rain: day.rain_total_mm,
      chance: day.rain_probability_max_pct,
    }));
  }
  return forecast.hourly.map((point) => ({
    label: placeDayTime(point.time, forecast.timezone_offset_seconds),
    temperature: point.temperature_c,
    rain: point.rain_mm,
    chance: point.rain_probability_pct,
  }));
}

interface ValueLine {
  name: string;
  value: string;
  color: string;
}

function ChartTooltip({ active, label, lines }: { active?: boolean; label?: string; lines: ValueLine[] }) {
  if (!active || lines.length === 0) return null;
  return (
    <div className="rounded border border-border bg-popover px-2.5 py-2 text-xs">
      <p className="font-mono text-muted-foreground">{label}</p>
      {lines.map((line) => (
        <p key={line.name} className="mt-1 flex items-center gap-1.5">
          <span className="size-2 rounded-[1px]" style={{ background: line.color }} aria-hidden="true" />
          {line.name} <span className="font-medium">{line.value}</span>
        </p>
      ))}
    </div>
  );
}

function ChartBlock({
  title,
  note,
  ariaLabel,
  legend,
  children,
}: {
  title: string;
  note: string;
  ariaLabel: string;
  legend?: ReactNode;
  children: ReactNode;
}) {
  return (
    <figure aria-label={ariaLabel}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-3">
        <span className="text-sm font-medium">
          {title} <span className="font-normal text-muted-foreground">{note}</span>
        </span>
        {legend}
      </figcaption>
      <div className="mt-2 h-36">{children}</div>
    </figure>
  );
}

function tooltipLines(
  payload: readonly { value?: unknown; dataKey?: unknown }[] | undefined,
  name: Record<string, { name: string; color: string; format: (value: number) => string }>,
): ValueLine[] {
  return (payload ?? []).flatMap((entry) => {
    const spec = name[String(entry.dataKey)];
    if (!spec || typeof entry.value !== "number") return [];
    return [{ name: spec.name, value: spec.format(entry.value), color: spec.color }];
  });
}

/**
 * Rain amount and rain chance are separate charts on purpose. A 90% chance of 0.2 mm and a 30% chance
 * of 25 mm are very different days, and a shared axis would invite reading one as the other.
 */
export function ForecastCharts({ forecast, view }: { forecast: Forecast; view: "hourly" | "daily" }) {
  const data = rows(forecast, view);
  const syncId = `forecast-${view}`;
  const ticks =
    view === "hourly"
      ? { minTickGap: 48, interval: "preserveStart" as const }
      : { interval: 0 as const };
  const margin = { top: 6, right: 12, bottom: 0, left: 0 };
  const rainTop = Math.max(Math.ceil(Math.max(0, ...data.map((row) => row.rain))), 2);
  const span = `${data[0]?.label ?? ""} to ${data[data.length - 1]?.label ?? ""}`;

  return (
    <div className="grid gap-6">
      <ChartBlock
        title="Temperature"
        note="°C"
        ariaLabel={`Temperature forecast, ${span}. The table below lists every value.`}
        legend={
          view === "daily" && (
            <span className="flex gap-3 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-3" style={{ background: COLOR.warm }} aria-hidden="true" />
                Daily high
              </span>
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0.5 w-3" style={{ background: COLOR.cool }} aria-hidden="true" />
                Daily low
              </span>
            </span>
          )
        }
      >
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} syncId={syncId} margin={margin}>
            <CartesianGrid vertical={false} stroke={COLOR.grid} />
            <XAxis {...X_AXIS_PROPS} {...AXIS_PROPS} {...ticks} />
            <YAxis {...AXIS_PROPS} width={36} domain={["auto", "auto"]} allowDecimals={false} />
            <Tooltip
              cursor={{ stroke: COLOR.axis, strokeWidth: 1 }}
              content={({ active, payload, label }) => (
                <ChartTooltip
                  active={active}
                  label={String(label)}
                  lines={tooltipLines(payload, {
                    temperature: { name: "Temperature", color: COLOR.warm, format: temp },
                    high: { name: "High", color: COLOR.warm, format: temp },
                    low: { name: "Low", color: COLOR.cool, format: temp },
                  })}
                />
              )}
            />
            {view === "hourly" ? (
              <Line
                dataKey="temperature"
                stroke={COLOR.warm}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4, stroke: COLOR.surface, strokeWidth: 2 }}
                isAnimationActive={false}
              />
            ) : (
              [
                <Line
                  key="high"
                  dataKey="high"
                  stroke={COLOR.warm}
                  strokeWidth={2}
                  dot={{ r: 3, fill: COLOR.warm, stroke: COLOR.surface, strokeWidth: 1 }}
                  isAnimationActive={false}
                />,
                <Line
                  key="low"
                  dataKey="low"
                  stroke={COLOR.cool}
                  strokeWidth={2}
                  dot={{ r: 3, fill: COLOR.cool, stroke: COLOR.surface, strokeWidth: 1 }}
                  isAnimationActive={false}
                />,
              ]
            )}
          </LineChart>
        </ResponsiveContainer>
      </ChartBlock>

      <ChartBlock
        title="Expected rain"
        note={view === "hourly" ? "millimetres in each 3 hours" : "millimetres per day"}
        ariaLabel={`Expected rainfall amount, ${span}. The table below lists every value.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} syncId={syncId} margin={margin} barCategoryGap={2}>
            <CartesianGrid vertical={false} stroke={COLOR.grid} />
            <XAxis {...X_AXIS_PROPS} {...AXIS_PROPS} {...ticks} />
            <YAxis {...AXIS_PROPS} width={36} domain={[0, rainTop]} ticks={[0, rainTop / 2, rainTop]} />
            <Tooltip
              cursor={{ fill: COLOR.grid, fillOpacity: 0.5 }}
              content={({ active, payload, label }) => (
                <ChartTooltip
                  active={active}
                  label={String(label)}
                  lines={tooltipLines(payload, {
                    rain: { name: "Expected rain", color: COLOR.rain, format: mm },
                  })}
                />
              )}
            />
            <Bar dataKey="rain" fill={COLOR.rain} radius={[3, 3, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </ChartBlock>

      <ChartBlock
        title="Chance of rain"
        note="%, says how likely rain is, not how much"
        ariaLabel={`Chance of rain as a percentage, ${span}. The table below lists every value.`}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} syncId={syncId} margin={margin}>
            <CartesianGrid vertical={false} stroke={COLOR.grid} />
            <XAxis {...X_AXIS_PROPS} {...AXIS_PROPS} {...ticks} />
            <YAxis {...AXIS_PROPS} width={36} domain={[0, 100]} ticks={[0, 50, 100]} />
            <Tooltip
              cursor={{ stroke: COLOR.axis, strokeWidth: 1 }}
              content={({ active, payload, label }) => (
                <ChartTooltip
                  active={active}
                  label={String(label)}
                  lines={tooltipLines(payload, {
                    chance: { name: "Chance of rain", color: COLOR.rain, format: percent },
                  })}
                />
              )}
            />
            <Area
              dataKey="chance"
              stroke={COLOR.rain}
              strokeWidth={2}
              fill={COLOR.rain}
              fillOpacity={0.1}
              dot={false}
              activeDot={{ r: 4, stroke: COLOR.surface, strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </ChartBlock>
    </div>
  );
}
