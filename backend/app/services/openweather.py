"""OpenWeatherMap HTTP client: retries, error mapping and payload validation.

This layer only speaks to the provider. Caching and provenance live in services/weather.py.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings
from app.core.errors import (
    WeatherAuthError,
    WeatherDataInvalidError,
    WeatherError,
    WeatherNotConfiguredError,
    WeatherRateLimitedError,
)
from app.schemas.weather import (
    CurrentWeather,
    DailyForecast,
    DataProvenance,
    Forecast,
    ForecastPoint,
    GeocodeResult,
    WeatherMeta,
)

logger = logging.getLogger("farmagent.weather")

SOURCE_NAME = "OpenWeatherMap"
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _RawCondition(_Lenient):
    description: str = "unknown"
    icon: str | None = None


class _RawMain(_Lenient):
    temp: float = Field(ge=-90, le=65)
    feels_like: float = Field(ge=-110, le=90)
    humidity: float = Field(ge=0, le=100)


class _RawWind(_Lenient):
    speed: float = Field(ge=0, le=120)
    deg: float | None = None
    gust: float | None = Field(default=None, ge=0, le=150)


class _RawCoord(_Lenient):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class _RawClouds(_Lenient):
    all: float | None = Field(default=None, ge=0, le=100)


class _RawCurrent(_Lenient):
    coord: _RawCoord
    weather: list[_RawCondition] = []
    main: _RawMain
    wind: _RawWind
    clouds: _RawClouds = _RawClouds()
    rain: dict[str, float] = {}
    dt: int
    timezone: int = 0
    name: str | None = None


class _RawForecastItem(_Lenient):
    dt: int
    main: _RawMain
    weather: list[_RawCondition] = []
    clouds: _RawClouds = _RawClouds()
    wind: _RawWind
    pop: float = Field(ge=0, le=1)
    rain: dict[str, float] = {}


class _RawCity(_Lenient):
    name: str | None = None
    coord: _RawCoord
    timezone: int = 0


class _RawForecast(_Lenient):
    items: list[_RawForecastItem] = Field(alias="list", min_length=1)
    city: _RawCity


class _RawGeocode(_Lenient):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    country: str | None = None
    state: str | None = None


def _timestamp(value: int) -> datetime:
    return datetime.fromtimestamp(value, UTC)


def _condition(conditions: list[_RawCondition]) -> _RawCondition:
    return conditions[0] if conditions else _RawCondition()


def parse_current(payload: Any, meta: WeatherMeta) -> CurrentWeather:
    try:
        raw = _RawCurrent.model_validate(payload)
    except ValidationError as exc:
        logger.warning("current weather payload failed validation: %s errors", exc.error_count())
        raise WeatherDataInvalidError() from None
    condition = _condition(raw.weather)
    return CurrentWeather(
        latitude=raw.coord.lat,
        longitude=raw.coord.lon,
        location_name=raw.name or None,
        temperature_c=raw.main.temp,
        feels_like_c=raw.main.feels_like,
        humidity_pct=raw.main.humidity,
        description=condition.description,
        icon=condition.icon,
        wind_speed_ms=raw.wind.speed,
        wind_gust_ms=raw.wind.gust,
        wind_direction_deg=raw.wind.deg,
        cloud_cover_pct=raw.clouds.all,
        rain_last_1h_mm=raw.rain.get("1h"),
        rain_last_3h_mm=raw.rain.get("3h"),
        observed_at=_timestamp(raw.dt),
        timezone_offset_seconds=raw.timezone,
        meta=meta,
    )


def parse_forecast(payload: Any, meta: WeatherMeta) -> Forecast:
    try:
        raw = _RawForecast.model_validate(payload)
    except ValidationError as exc:
        logger.warning("forecast payload failed validation: %s errors", exc.error_count())
        raise WeatherDataInvalidError() from None
    points = [
        ForecastPoint(
            time=_timestamp(item.dt),
            temperature_c=item.main.temp,
            feels_like_c=item.main.feels_like,
            humidity_pct=item.main.humidity,
            wind_speed_ms=item.wind.speed,
            wind_gust_ms=item.wind.gust,
            cloud_cover_pct=item.clouds.all,
            # The provider omits "rain" when none is forecast for the period.
            rain_mm=item.rain.get("3h", 0.0),
            rain_probability_pct=round(item.pop * 100, 1),
            description=_condition(item.weather).description,
        )
        for item in raw.items
    ]
    offset = raw.city.timezone
    return Forecast(
        latitude=raw.city.coord.lat,
        longitude=raw.city.coord.lon,
        location_name=raw.city.name or None,
        timezone_offset_seconds=offset,
        horizon_hours=len(points) * 3,
        hourly=points,
        daily=aggregate_daily(points, offset),
        meta=meta,
    )


def aggregate_daily(points: list[ForecastPoint], offset_seconds: int) -> list[DailyForecast]:
    """Group forecast points into calendar days in the location's own timezone."""
    groups: dict[Any, list[ForecastPoint]] = {}
    for point in points:
        local_day = (point.time + timedelta(seconds=offset_seconds)).date()
        groups.setdefault(local_day, []).append(point)

    days = []
    for day, group in sorted(groups.items()):
        descriptions = [p.description for p in group]
        days.append(
            DailyForecast(
                date=day,
                temp_min_c=min(p.temperature_c for p in group),
                temp_max_c=max(p.temperature_c for p in group),
                humidity_mean_pct=round(sum(p.humidity_pct for p in group) / len(group), 1),
                wind_max_ms=max(p.wind_speed_ms for p in group),
                rain_total_mm=round(sum(p.rain_mm for p in group), 2),
                rain_probability_max_pct=max(p.rain_probability_pct for p in group),
                description=max(set(descriptions), key=descriptions.count),
                periods=len(group),
            )
        )
    return days


class OpenWeatherClient:
    def __init__(self, http: httpx.AsyncClient, settings: Settings) -> None:
        self._http = http
        self._settings = settings

    async def _get(self, path: str, params: dict[str, Any]) -> Any:
        key = self._settings.openweather_api_key
        if key is None:
            raise WeatherNotConfiguredError()

        url = f"{self._settings.openweather_base_url.rstrip('/')}{path}"
        query = {**params, "appid": key.get_secret_value()}
        attempts = self._settings.openweather_max_retries + 1

        for attempt in range(attempts):
            is_last = attempt == attempts - 1
            try:
                response = await self._http.get(
                    url, params=query, timeout=self._settings.openweather_timeout_seconds
                )
            except httpx.TransportError as exc:
                # The exception's message can contain the request URL, and with it the API key.
                logger.warning("weather request failed type=%s path=%s", type(exc).__name__, path)
                if is_last:
                    raise WeatherError() from None
                await self._backoff(attempt)
                continue

            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError:
                    raise WeatherDataInvalidError() from None
            if response.status_code == 401:
                raise WeatherAuthError()
            if response.status_code in _RETRYABLE_STATUS and not is_last:
                await self._backoff(attempt)
                continue
            if response.status_code == 429:
                raise WeatherRateLimitedError()
            logger.warning("weather provider status=%s path=%s", response.status_code, path)
            raise WeatherError()

        raise WeatherError()

    async def _backoff(self, attempt: int) -> None:
        await asyncio.sleep(self._settings.openweather_retry_backoff_seconds * (2**attempt))

    async def fetch_current(self, latitude: float, longitude: float) -> Any:
        return await self._get(
            "/data/2.5/weather", {"lat": latitude, "lon": longitude, "units": "metric"}
        )

    async def fetch_forecast(self, latitude: float, longitude: float) -> Any:
        return await self._get(
            "/data/2.5/forecast", {"lat": latitude, "lon": longitude, "units": "metric"}
        )

    async def geocode(self, query: str, limit: int = 5) -> list[GeocodeResult]:
        payload = await self._get("/geo/1.0/direct", {"q": query, "limit": limit})
        return self._parse_geocode(payload)

    async def reverse_geocode(
        self, latitude: float, longitude: float, limit: int = 1
    ) -> list[GeocodeResult]:
        payload = await self._get(
            "/geo/1.0/reverse", {"lat": latitude, "lon": longitude, "limit": limit}
        )
        return self._parse_geocode(payload)

    @staticmethod
    def _parse_geocode(payload: Any) -> list[GeocodeResult]:
        try:
            raw = [_RawGeocode.model_validate(item) for item in payload]
        except (ValidationError, TypeError):
            raise WeatherDataInvalidError() from None
        return [
            GeocodeResult(
                name=item.name,
                state=item.state,
                country=item.country,
                latitude=item.lat,
                longitude=item.lon,
            )
            for item in raw
        ]


def live_meta(fetched_at: datetime) -> WeatherMeta:
    return WeatherMeta(
        provenance=DataProvenance.LIVE, source=SOURCE_NAME, fetched_at=fetched_at, age_seconds=0
    )
