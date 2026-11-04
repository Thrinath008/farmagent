"""Scenario Lab weather. Everything from this provider is labelled simulated, and nothing else uses it.

The fixed reference time keeps scenario results identical between runs.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.schemas.weather import (
    CurrentWeather,
    DataProvenance,
    Forecast,
    ForecastPoint,
    GeocodeResult,
    WeatherMeta,
)
from app.services.openweather import aggregate_daily

SIMULATED_SOURCE = "Simulated (Scenario Lab)"
REFERENCE_TIME = datetime(2027, 1, 15, 6, 0, tzinfo=UTC)
_LATITUDE = 30.9
_LONGITUDE = 75.85
_PERIODS = 16  # 48 hours of 3-hourly periods
_RAIN_PERIODS = 5


@dataclass(frozen=True)
class SimulatedConditions:
    temperature_c: float
    humidity_pct: float
    rain_probability_pct: float
    expected_rain_mm: float
    wind_speed_ms: float
    description: str


def _meta() -> WeatherMeta:
    return WeatherMeta(
        provenance=DataProvenance.SIMULATED,
        source=SIMULATED_SOURCE,
        observed_at=REFERENCE_TIME,
        fetched_at=REFERENCE_TIME,
        warning="Simulated demonstration data, not real weather.",
    )


class SimulatedWeatherProvider:
    def __init__(self, conditions: SimulatedConditions) -> None:
        self._c = conditions

    async def get_current(
        self, latitude: float, longitude: float, *, force_refresh: bool = False
    ) -> CurrentWeather:
        c = self._c
        return CurrentWeather(
            latitude=latitude,
            longitude=longitude,
            location_name="Simulated location",
            temperature_c=c.temperature_c,
            feels_like_c=c.temperature_c,
            humidity_pct=c.humidity_pct,
            description=c.description,
            wind_speed_ms=c.wind_speed_ms,
            observed_at=REFERENCE_TIME,
            meta=_meta(),
        )

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        *,
        horizon_hours: int = 48,
        force_refresh: bool = False,
    ) -> Forecast:
        c = self._c
        per_period = c.expected_rain_mm / _RAIN_PERIODS if c.expected_rain_mm else 0.0
        points = [
            ForecastPoint(
                time=REFERENCE_TIME + timedelta(hours=3 * (i + 1)),
                temperature_c=c.temperature_c,
                humidity_pct=c.humidity_pct,
                wind_speed_ms=c.wind_speed_ms,
                rain_mm=per_period if i < _RAIN_PERIODS else 0.0,
                rain_probability_pct=c.rain_probability_pct,
                description=c.description,
            )
            for i in range(_PERIODS)
        ]
        return Forecast(
            latitude=latitude,
            longitude=longitude,
            location_name="Simulated location",
            horizon_hours=48,
            hourly=points,
            daily=aggregate_daily(points, 0),
            meta=_meta(),
        )

    async def geocode(self, query: str, limit: int = 5) -> list[GeocodeResult]:
        return [
            GeocodeResult(
                name="Simulated location",
                state="Scenario Lab",
                country="N/A",
                latitude=_LATITUDE,
                longitude=_LONGITUDE,
            )
        ]

    async def reverse_geocode(self, latitude: float, longitude: float) -> list[GeocodeResult]:
        return await self.geocode("")


SCENARIO_COORDINATES = (_LATITUDE, _LONGITUDE)
