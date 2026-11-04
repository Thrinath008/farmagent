import { calendarDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { IrrigationSchedule } from "@/types/api";

const DAY_MS = 86_400_000;

function dayNumber(value: string): number {
  return Date.parse(`${value.slice(0, 10)}T00:00:00Z`) / DAY_MS;
}

function monthTicks(start: number, end: number) {
  const ticks: { day: number; label: string }[] = [];
  const cursor = new Date(start * DAY_MS);
  cursor.setUTCDate(1);
  cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  while (cursor.getTime() / DAY_MS < end) {
    ticks.push({
      day: cursor.getTime() / DAY_MS,
      label: new Intl.DateTimeFormat("en-IN", { timeZone: "UTC", month: "short" }).format(cursor),
    });
    cursor.setUTCMonth(cursor.getUTCMonth() + 1);
  }
  return ticks;
}

/**
 * The crop's season as a strip: sowing on the left, the last irrigation date on the right, and the
 * published irrigation windows laid out at their real dates, with today marked.
 */
export function SeasonStrip({
  schedule,
  cropName,
  className,
}: {
  schedule: IrrigationSchedule;
  cropName: string;
  className?: string;
}) {
  const start = dayNumber(schedule.sowing_date);
  const end = dayNumber(schedule.last_irrigation_by);
  const span = Math.max(end - start, 1);
  const position = (day: number) => `${Math.min(Math.max((day - start) / span, 0), 1) * 100}%`;
  const today = start + schedule.days_after_sowing;
  const pastSeason = today > end;
  const beforeSowing = today < start;
  const active = schedule.in_window?.number ?? null;
  const next = schedule.next_window?.number ?? null;

  return (
    <figure className={className}>
      <figcaption className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <span className="display text-base">{cropName} irrigation season</span>
        <span className="text-sm text-muted-foreground">
          {beforeSowing
            ? `Sowing on ${calendarDate(schedule.sowing_date)}`
            : `Day ${schedule.days_after_sowing} after sowing`}
        </span>
      </figcaption>

      <div className="mt-7 mb-1" aria-hidden="true" data-testid="season-track">
        <div className="relative h-11 rounded-[2px] border border-border bg-muted">
          {!beforeSowing && (
            <div
              className="absolute inset-y-0 left-0 bg-sage"
              style={{ width: position(today) }}
              data-testid="season-elapsed"
            />
          )}
          {schedule.windows.map((window) => {
            const from = dayNumber(window.start_date);
            const to = dayNumber(window.end_date);
            const isActive = window.number === active;
            const isDone = dayNumber(window.end_date) < today;
            return (
              <div
                key={window.number}
                className={cn(
                  "absolute inset-y-1 flex min-w-5 items-center justify-center rounded-[1px] font-mono text-xs font-medium",
                  isActive
                    ? "bg-forest text-white ring-2 ring-shoot"
                    : isDone
                      ? "bg-shoot/30 text-ink"
                      : "bg-shoot-ink text-white",
                )}
                style={{ left: position(from), width: `${((to - from + 1) / span) * 100}%` }}
                data-testid={`season-window-${window.number}`}
              >
                {window.number}
              </div>
            );
          })}
          {!pastSeason && !beforeSowing && (
            <div className="absolute -top-5 bottom-0 w-px bg-ink" style={{ left: position(today) }}>
              <span
                className={cn(
                  "absolute -top-0.5 font-mono text-[0.6875rem] font-medium whitespace-nowrap",
                  (today - start) / span > 0.85 ? "right-1" : "left-1",
                )}
              >
                Today
              </span>
            </div>
          )}
        </div>
        <div className="relative mt-1 h-4 font-mono text-[0.6875rem] text-muted-foreground">
          {monthTicks(start, end).map((tick) => (
            <span key={tick.day} className="absolute -translate-x-1/2" style={{ left: position(tick.day) }}>
              {tick.label}
            </span>
          ))}
        </div>
      </div>

      <ol className="sr-only">
        {schedule.windows.map((window) => (
          <li key={window.number}>
            Irrigation {window.number}: {calendarDate(window.start_date)} to{" "}
            {calendarDate(window.end_date)}. {window.basis}.
          </li>
        ))}
      </ol>

      <p className="mt-2 text-sm">
        {schedule.in_window ? (
          <>
            <strong className="font-semibold">Irrigation {active} window is open</strong> until{" "}
            {calendarDate(schedule.in_window.end_date)}. {schedule.in_window.basis}.
          </>
        ) : schedule.next_window ? (
          <>
            <strong className="font-semibold">Next is irrigation {next}</strong>, from{" "}
            {calendarDate(schedule.next_window.start_date)} to{" "}
            {calendarDate(schedule.next_window.end_date)}. {schedule.next_window.basis}.
          </>
        ) : (
          <>
            All listed irrigation windows have passed. Last irrigation by{" "}
            {calendarDate(schedule.last_irrigation_by)}.
          </>
        )}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        Numbered blocks are irrigation windows from the PAU Package of Practices timetable, assuming
        earlier irrigations ran on time.
      </p>
    </figure>
  );
}
