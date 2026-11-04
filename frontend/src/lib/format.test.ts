import { describe, expect, it } from "vitest";
import type { ForecastPoint } from "@/types/api";
import {
  age,
  calendarDate,
  mm,
  MISSING,
  next24Hours,
  percent,
  placeDayTime,
  placeTime,
  secondsSince,
  signed,
  temp,
  windKmh,
} from "./format";

describe("missing values", () => {
  it("shows a dash for a missing reading", () => {
    for (const format of [temp, percent, mm, windKmh]) {
      expect(format(null)).toBe(MISSING);
      expect(format(undefined)).toBe(MISSING);
    }
  });

  it("keeps a measured zero distinct from a missing reading", () => {
    expect(mm(0)).toBe("0 mm");
    expect(percent(0)).toBe("0%");
    expect(temp(0)).toBe("0°C");
    expect(windKmh(0)).toBe("0 km/h");
  });

  it("has no age for a missing time", () => {
    expect(secondsSince(null)).toBeNull();
  });
});

describe("units", () => {
  it("converts metres per second to km/h", () => {
    expect(windKmh(5)).toBe("18 km/h");
  });

  it("signs the rule score with a real minus", () => {
    expect(signed(2)).toBe("+2");
    expect(signed(-1)).toBe("−1");
    expect(signed(0)).toBe("0");
  });
});

describe("place time", () => {
  it("shows forecast times on the farm's clock, whatever the browser's zone", () => {
    const iso = "2026-11-05T00:00:00Z";
    expect(placeTime(iso, 19800)).toBe("05:30");
    expect(placeTime(iso, 0)).toBe("00:00");
    expect(placeTime(iso, -18000)).toBe("19:00");
  });

  it("rolls the day over with the offset", () => {
    expect(placeDayTime("2026-11-05T20:00:00Z", 19800)).toBe("Fri, 01:30");
  });

  it("never moves a calendar date", () => {
    expect(calendarDate("2026-11-05")).toBe("5 Nov");
    expect(calendarDate("2026-11-05T23:59:00Z")).toBe("5 Nov");
  });
});

describe("age", () => {
  it("names the size of the age", () => {
    expect(age(30)).toBe("just now");
    expect(age(60)).toBe("1 min ago");
    expect(age(3600)).toBe("1 h ago");
    expect(age(90000)).toBe("1 d ago");
  });
});

describe("next24Hours", () => {
  it("keeps the chance of rain and the amount apart", () => {
    const period = (rain_mm: number, rain_probability_pct: number) => ({ rain_mm, rain_probability_pct });
    const hourly = [period(0.2, 90), period(1, 30)] as ForecastPoint[];
    expect(next24Hours({ hourly })).toEqual({ chance: 90, rain: 1.2 });
  });

  it("has neither when there is no forecast", () => {
    expect(next24Hours(undefined)).toEqual({ chance: null, rain: null });
    expect(next24Hours({ hourly: [] })).toEqual({ chance: null, rain: null });
  });
});
