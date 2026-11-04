"""Weather service: database cache plus honest provenance labelling.

The contract, relied on by the decision engine and the agent:

- `live` means the provider answered during this request.
- `cached` means a stored provider response. It is flagged stale when its window has passed.
- A provider failure falls back to recent cached data with a warning, otherwise it raises.
  It never falls back to simulated data.
"""

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.errors import WeatherError, WeatherNotConfiguredError
from app.database.session import SessionFactory
from app.models import WeatherCache
from app.schemas.weather import (
    CurrentWeather,
    DataProvenance,
    Forecast,
    GeocodeResult,
    WeatherMeta,
)
from app.services.openweather import (
    SOURCE_NAME,
    OpenWeatherClient,
    aggregate_daily,
    live_meta,
    parse_current,
    parse_forecast,
)

logger = logging.getLogger("farmagent.weather")

MAX_FORECAST_HOURS = 120


class WeatherProvider(Protocol):
    """What tools and assessments depend on. Live and simulated providers both implement it."""

    async def get_current(
        self, latitude: float, longitude: float, *, force_refresh: bool = False
    ) -> CurrentWeather: ...

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        *,
        horizon_hours: int = MAX_FORECAST_HOURS,
        force_refresh: bool = False,
    ) -> Forecast: ...

    async def geocode(self, query: str, limit: int = 5) -> list[GeocodeResult]: ...

    async def reverse_geocode(self, latitude: float, longitude: float) -> list[GeocodeResult]: ...


def cache_key(kind: str, latitude: float, longitude: float) -> str:
    # Two decimals is about a kilometre, finer than the provider's own grid.
    return f"{kind}:{latitude:.2f}:{longitude:.2f}"


class WeatherService:
    def __init__(
        self,
        client: OpenWeatherClient,
        session_factory: SessionFactory,
        settings: Settings,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._client = client
        self._sessions = session_factory
        self._settings = settings
        self._clock = clock

    async def get_current(
        self, latitude: float, longitude: float, *, force_refresh: bool = False
    ) -> CurrentWeather:
        document = await self._load(
            kind="current",
            latitude=latitude,
            longitude=longitude,
            fetch=lambda: self._client.fetch_current(latitude, longitude),
            parse=lambda raw, fetched: parse_current(raw, live_meta(fetched)).model_dump(
                mode="json"
            ),
            ttl=self._settings.weather_current_ttl_seconds,
            force_refresh=force_refresh,
        )
        weather = CurrentWeather.model_validate(document)
        now = self._clock()
        age = max(int((now - weather.observed_at).total_seconds()), 0)
        weather.meta.observed_at = weather.observed_at
        weather.meta.age_seconds = age
        if age > self._settings.weather_stale_after_seconds:
            weather.meta.is_stale = True
            weather.meta.warning = weather.meta.warning or (
                f"The latest observation is {age // 3600} hours old and may not reflect "
                "current conditions."
            )
        return weather

    async def get_forecast(
        self,
        latitude: float,
        longitude: float,
        *,
        horizon_hours: int = MAX_FORECAST_HOURS,
        force_refresh: bool = False,
    ) -> Forecast:
        document = await self._load(
            kind="forecast",
            latitude=latitude,
            longitude=longitude,
            fetch=lambda: self._client.fetch_forecast(latitude, longitude),
            parse=lambda raw, fetched: parse_forecast(raw, live_meta(fetched)).model_dump(
                mode="json"
            ),
            ttl=self._settings.weather_forecast_ttl_seconds,
            force_refresh=force_refresh,
        )
        forecast = Forecast.model_validate(document)
        return self._window(forecast, horizon_hours)

    def _window(self, forecast: Forecast, horizon_hours: int) -> Forecast:
        """Drop elapsed periods (a cached forecast ages) and clip to the requested horizon."""
        now = self._clock()
        horizon = min(horizon_hours, MAX_FORECAST_HOURS)
        start = now - timedelta(hours=forecast.resolution_hours)
        end = now + timedelta(hours=horizon)
        points = [p for p in forecast.hourly if start < p.time <= end]
        if not points:
            raise WeatherError("The stored forecast has expired and no newer one is available.")
        forecast.hourly = points
        forecast.daily = aggregate_daily(points, forecast.timezone_offset_seconds)
        forecast.horizon_hours = horizon
        return forecast

    async def geocode(self, query: str, limit: int = 5) -> list[GeocodeResult]:
        return await self._client.geocode(query, limit)

    async def reverse_geocode(self, latitude: float, longitude: float) -> list[GeocodeResult]:
        return await self._client.reverse_geocode(latitude, longitude)

    async def _load(
        self,
        *,
        kind: str,
        latitude: float,
        longitude: float,
        fetch: Callable[[], Awaitable[Any]],
        parse: Callable[[Any, datetime], dict],
        ttl: int,
        force_refresh: bool,
    ) -> dict:
        key = cache_key(kind, latitude, longitude)
        now = self._clock()
        cached = await self._read_cache(key)

        if cached is not None and not force_refresh and cached.expires_at > now:
            return self._from_cache(cached, now)

        try:
            document = parse(await fetch(), now)
        except WeatherNotConfiguredError:
            raise
        except WeatherError as exc:
            max_age = timedelta(seconds=self._settings.weather_cache_max_age_seconds)
            if cached is not None and now - cached.fetched_at <= max_age:
                logger.warning("serving stale cache after provider error code=%s", exc.code)
                return self._from_cache(cached, now, refresh_failed=True)
            raise

        await self._write_cache(key, kind, latitude, longitude, document, now, ttl)
        return document

    def _from_cache(self, row: WeatherCache, now: datetime, refresh_failed: bool = False) -> dict:
        age_minutes = int((now - row.fetched_at).total_seconds() // 60)
        expired = row.expires_at <= now
        warning = None
        if refresh_failed:
            retrieved = (
                "less than a minute ago"
                if age_minutes < 1
                else f"{age_minutes} minute{'s' if age_minutes != 1 else ''} ago"
            )
            warning = (
                f"Live weather could not be refreshed. This data was retrieved {retrieved} "
                "and may be out of date."
            )
        document = dict(row.payload)
        document["meta"] = WeatherMeta(
            provenance=DataProvenance.CACHED,
            source=row.source,
            observed_at=row.observed_at,
            fetched_at=row.fetched_at,
            age_seconds=int((now - (row.observed_at or row.fetched_at)).total_seconds()),
            is_stale=expired,
            warning=warning,
        ).model_dump(mode="json")
        return document

    async def _read_cache(self, key: str) -> WeatherCache | None:
        try:
            async with self._sessions() as session:
                return await session.scalar(
                    select(WeatherCache).where(WeatherCache.cache_key == key)
                )
        except SQLAlchemyError as exc:
            # A cache outage should not take live weather down with it.
            logger.warning("weather cache read failed type=%s", type(exc).__name__)
            return None

    async def _write_cache(
        self,
        key: str,
        kind: str,
        latitude: float,
        longitude: float,
        document: dict,
        now: datetime,
        ttl: int,
    ) -> None:
        observed = document.get("observed_at")
        values = {
            "cache_key": key,
            "kind": kind,
            "latitude": latitude,
            "longitude": longitude,
            "source": SOURCE_NAME,
            "payload": document,
            "observed_at": datetime.fromisoformat(observed) if observed else None,
            "fetched_at": now,
            "expires_at": now + timedelta(seconds=ttl),
        }
        try:
            async with self._sessions() as session:
                insert = (
                    pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert
                )
                statement = insert(WeatherCache).values(**values)
                # Dashboard pages ask for the same location concurrently, hence a real upsert.
                statement = statement.on_conflict_do_update(
                    index_elements=[WeatherCache.cache_key],
                    set_={k: v for k, v in values.items() if k != "cache_key"},
                )
                await session.execute(statement)
                await session.commit()
        except SQLAlchemyError as exc:
            logger.warning("weather cache write failed type=%s", type(exc).__name__)
