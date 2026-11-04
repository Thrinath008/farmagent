"""Normalized weather models. Every value carries provenance: live, cached or simulated."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DataProvenance(StrEnum):
    LIVE = "live"
    CACHED = "cached"
    SIMULATED = "simulated"
    UNAVAILABLE = "unavailable"


class WeatherMeta(BaseModel):
    provenance: DataProvenance
    source: str
    observed_at: datetime | None = None
    fetched_at: datetime | None = None
    age_seconds: int | None = None
    is_stale: bool = False
    warning: str | None = None


class CurrentWeather(BaseModel):
    latitude: float
    longitude: float
    location_name: str | None = None
    temperature_c: float
    feels_like_c: float
    humidity_pct: float
    description: str
    icon: str | None = None
    wind_speed_ms: float
    wind_gust_ms: float | None = None
    wind_direction_deg: float | None = None
    cloud_cover_pct: float | None = None
    # None means the provider reported nothing for this period, which is not a measured zero.
    rain_last_1h_mm: float | None = None
    rain_last_3h_mm: float | None = None
    observed_at: datetime
    timezone_offset_seconds: int = 0
    meta: WeatherMeta


class ForecastPoint(BaseModel):
    time: datetime
    temperature_c: float
    feels_like_c: float | None = None
    humidity_pct: float
    wind_speed_ms: float
    wind_gust_ms: float | None = None
    cloud_cover_pct: float | None = None
    rain_mm: float = Field(description="Forecast rainfall amount for this period, in mm.")
    rain_probability_pct: float = Field(
        description="Probability of precipitation for this period. Not an amount."
    )
    description: str


class DailyForecast(BaseModel):
    date: date
    temp_min_c: float
    temp_max_c: float
    humidity_mean_pct: float
    wind_max_ms: float
    rain_total_mm: float
    rain_probability_max_pct: float
    description: str
    periods: int


class Forecast(BaseModel):
    latitude: float
    longitude: float
    location_name: str | None = None
    timezone_offset_seconds: int = 0
    resolution_hours: int = 3
    horizon_hours: int
    hourly: list[ForecastPoint]
    daily: list[DailyForecast]
    meta: WeatherMeta


class GeocodeResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    state: str | None = None
    country: str | None = None
    latitude: float
    longitude: float
    timezone_offset_seconds: int | None = None


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]
