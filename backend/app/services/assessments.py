"""Fetch validated weather, then assess. Shared by the REST endpoints and the agent's tools.

Assessments only ever read weather through here. That is how "no weather-dependent advice without
validated weather" is enforced: there is no way to hand the engine weather numbers from elsewhere.
"""

import asyncio
from dataclasses import dataclass, field

from app.core.errors import AppError, WeatherError
from app.intelligence.types import WeatherSnapshot
from app.intelligence.weather_analysis import build_snapshot
from app.schemas.weather import CurrentWeather, Forecast
from app.services.weather import WeatherProvider


@dataclass
class WeatherBundle:
    current: CurrentWeather | None = None
    forecast: Forecast | None = None
    errors: list[AppError] = field(default_factory=list)

    @property
    def snapshot(self) -> WeatherSnapshot | None:
        return build_snapshot(self.current, self.forecast)


async def load_weather(
    provider: WeatherProvider, latitude: float, longitude: float, *, force_refresh: bool = False
) -> WeatherBundle:
    """Load both feeds. One failing leaves the other usable, and the assessment says what is missing."""
    outcomes = await asyncio.gather(
        provider.get_current(latitude, longitude, force_refresh=force_refresh),
        provider.get_forecast(latitude, longitude, force_refresh=force_refresh),
        return_exceptions=True,
    )
    bundle = WeatherBundle()
    for outcome in outcomes:
        if isinstance(outcome, WeatherError):
            bundle.errors.append(outcome)
        elif isinstance(outcome, BaseException):
            raise outcome
        elif isinstance(outcome, CurrentWeather):
            bundle.current = outcome
        else:
            bundle.forecast = outcome
    return bundle
