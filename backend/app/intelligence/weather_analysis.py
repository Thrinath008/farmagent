"""Reduce validated weather into the snapshot assessments read, including an ET0 estimate."""

import math
from datetime import date

from app.intelligence.types import ForecastConditions, WeatherSnapshot
from app.schemas.weather import CurrentWeather, DataProvenance, Forecast

_SOLAR_CONSTANT = 0.0820  # MJ m-2 min-1, FAO-56
_MJ_TO_MM = 0.408  # MJ m-2 day-1 to mm/day equivalent, FAO-56
_FULL_DAY_PERIODS = 7  # of the eight 3-hourly periods, enough for a usable daily min and max


def extraterrestrial_radiation_mj(latitude_deg: float, day: date) -> float:
    """Daily extraterrestrial radiation Ra, FAO-56 equation 21."""
    lat = math.radians(latitude_deg)
    doy = day.timetuple().tm_yday
    dr = 1 + 0.033 * math.cos(2 * math.pi * doy / 365)
    declination = 0.409 * math.sin(2 * math.pi * doy / 365 - 1.39)
    ws = math.acos(max(-1.0, min(1.0, -math.tan(lat) * math.tan(declination))))
    return (
        24
        * 60
        / math.pi
        * _SOLAR_CONSTANT
        * dr
        * (
            ws * math.sin(lat) * math.sin(declination)
            + math.cos(lat) * math.cos(declination) * math.sin(ws)
        )
    )


def hargreaves_et0(tmin_c: float, tmax_c: float, latitude_deg: float, day: date) -> float | None:
    """Reference evapotranspiration in mm/day, FAO-56 equation 52. An estimate from temperature."""
    if tmax_c < tmin_c:
        return None
    ra = extraterrestrial_radiation_mj(latitude_deg, day) * _MJ_TO_MM
    return round(
        max(0.0023 * ((tmin_c + tmax_c) / 2 + 17.8) * math.sqrt(tmax_c - tmin_c) * ra, 0.0), 2
    )


def _estimate_et0(forecast: Forecast) -> float | None:
    """Mean ET0 across complete forecast days. Partial days understate the diurnal range."""
    values = []
    for day in forecast.daily:
        if day.periods < _FULL_DAY_PERIODS or day.temp_max_c - day.temp_min_c < 1:
            continue
        et0 = hargreaves_et0(day.temp_min_c, day.temp_max_c, forecast.latitude, day.date)
        if et0 is not None:
            values.append(et0)
    return round(sum(values) / len(values), 2) if values else None


def _merge_provenance(*values: DataProvenance) -> DataProvenance:
    """Report the weakest source in use, so mixed data never reads as fully live."""
    for candidate in (
        DataProvenance.SIMULATED,
        DataProvenance.CACHED,
        DataProvenance.LIVE,
    ):
        if candidate in values:
            return candidate
    return DataProvenance.UNAVAILABLE


def build_snapshot(
    current: CurrentWeather | None, forecast: Forecast | None
) -> WeatherSnapshot | None:
    """Combine what was retrieved. Returns None when no validated weather exists at all."""
    if current is None and forecast is None:
        return None

    metas = [item.meta for item in (current, forecast) if item is not None]
    snapshot = WeatherSnapshot(
        provenance=_merge_provenance(*(m.provenance for m in metas)),
        source=" + ".join(sorted({m.source for m in metas})),
        observed_at=current.observed_at if current else metas[0].fetched_at,
        is_stale=any(m.is_stale for m in metas),
        warning=next((m.warning for m in metas if m.warning), None),
    )

    if current is not None:
        snapshot.location_name = current.location_name
        snapshot.latitude = current.latitude
        snapshot.longitude = current.longitude
        snapshot.description = current.description
        snapshot.temperature_c = current.temperature_c
        snapshot.feels_like_c = current.feels_like_c
        snapshot.humidity_pct = current.humidity_pct
        snapshot.wind_speed_ms = current.wind_speed_ms
        snapshot.rain_last_1h_mm = current.rain_last_1h_mm

    if forecast is not None and forecast.hourly:
        snapshot.location_name = snapshot.location_name or forecast.location_name
        snapshot.latitude = (
            snapshot.latitude if snapshot.latitude is not None else forecast.latitude
        )
        snapshot.longitude = (
            snapshot.longitude if snapshot.longitude is not None else forecast.longitude
        )
        points = forecast.hourly
        step = forecast.resolution_hours
        next_24 = points[: 24 // step]
        next_48 = points[: 48 // step]
        snapshot.forecast_available = True
        snapshot.rain_next_24h_mm = round(sum(p.rain_mm for p in next_24), 2)
        snapshot.rain_next_48h_mm = round(sum(p.rain_mm for p in next_48), 2)
        snapshot.rain_prob_max_24h_pct = max(p.rain_probability_pct for p in next_24)
        snapshot.rain_prob_max_48h_pct = max(p.rain_probability_pct for p in next_48)
        snapshot.temp_max_48h_c = max(p.temperature_c for p in next_48)
        snapshot.temp_min_48h_c = min(p.temperature_c for p in next_48)
        snapshot.humidity_mean_48h_pct = round(
            sum(p.humidity_pct for p in next_48) / len(next_48), 1
        )
        snapshot.wind_max_24h_ms = max(p.wind_speed_ms for p in next_24)
        snapshot.et0_mm_day = _estimate_et0(forecast)
        snapshot.periods = [
            ForecastConditions(
                time=p.time,
                temperature_c=p.temperature_c,
                humidity_pct=p.humidity_pct,
                rain_mm=p.rain_mm,
            )
            for p in points
        ]
    return snapshot
