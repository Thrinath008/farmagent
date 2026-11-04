import type { Forecast } from "@/types/api";

const LOCALE = "en-IN";

/** An em dash, because a missing reading must never look like a measured zero. */
export const MISSING = "—";

function number(value: number | null | undefined, digits: number): string {
  if (value === null || value === undefined || Number.isNaN(value)) return MISSING;
  return value.toLocaleString(LOCALE, { maximumFractionDigits: digits });
}

export const temp = (value: number | null | undefined) =>
  value === null || value === undefined ? MISSING : `${number(value, 0)}°C`;
export const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? MISSING : `${number(value, 0)}%`;
export const mm = (value: number | null | undefined) =>
  value === null || value === undefined ? MISSING : `${number(value, 1)} mm`;
export const windKmh = (metresPerSecond: number | null | undefined) =>
  metresPerSecond === null || metresPerSecond === undefined
    ? MISSING
    : `${number(metresPerSecond * 3.6, 0)} km/h`;

export function secondsSince(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.max(Math.floor((Date.now() - new Date(iso).getTime()) / 1000), 0);
}

export function age(seconds: number): string {
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

// Forecast times are shown in the farm's timezone, not the browser's. A forecast for Punjab viewed
// from elsewhere must still say when the rain falls in Punjab. Shifting by the location's offset and
// formatting as UTC gives that clock without needing the zone's name.
function shifted(iso: string, offsetSeconds: number): Date {
  return new Date(new Date(iso).getTime() + offsetSeconds * 1000);
}

export function placeTime(iso: string, offsetSeconds: number): string {
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(shifted(iso, offsetSeconds));
}

export function placeDayTime(iso: string, offsetSeconds: number): string {
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: "UTC",
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(shifted(iso, offsetSeconds));
}

/** A date-only value such as a sowing date. It names a calendar day, so no zone may shift it. */
export function calendarDate(value: string, options?: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(LOCALE, {
    timeZone: "UTC",
    day: "numeric",
    month: "short",
    ...options,
  }).format(new Date(`${value.slice(0, 10)}T00:00:00Z`));
}

export function calendarDay(value: string): string {
  return calendarDate(value, { weekday: "short" });
}

export function dateTime(iso: string): string {
  return new Intl.DateTimeFormat(LOCALE, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
}

export function todayIso(): string {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

export function words(value: string | null | undefined): string {
  if (!value) return MISSING;
  const text = value.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function sentence(value: string | null | undefined): string {
  if (!value) return MISSING;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function coordinates(latitude: number, longitude: number): string {
  return `${latitude.toFixed(3)}, ${longitude.toFixed(3)}`;
}

export function placeTitle(place: {
  name: string | null;
  state: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
}): string {
  return (
    [place.name, place.state, place.country].filter(Boolean).join(", ") ||
    coordinates(place.latitude, place.longitude)
  );
}

export function signed(value: number): string {
  return value > 0 ? `+${value}` : value < 0 ? `−${Math.abs(value)}` : "0";
}

/** The forecast's first 24 hours. Chance and amount stay separate, because they mean different things. */
export function next24Hours(forecast: Pick<Forecast, "hourly"> | undefined) {
  const periods = forecast?.hourly.slice(0, 8) ?? [];
  if (periods.length === 0) return { chance: null, rain: null };
  return {
    chance: Math.max(...periods.map((p) => p.rain_probability_pct)),
    rain: periods.reduce((sum, p) => sum + p.rain_mm, 0),
  };
}

export function placeName(place: {
  location_name?: string | null;
  state?: string | null;
  country?: string | null;
}): string | null {
  const parts = [place.location_name, place.state, place.country].filter(Boolean);
  return parts.length ? parts.join(", ") : null;
}
