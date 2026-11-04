"""Weather endpoints. Failures surface as errors. Mock data is never substituted."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import WeatherDep
from app.core.errors import BadRequestError
from app.core.text import clean_text
from app.schemas.weather import CurrentWeather, Forecast, GeocodeResponse

router = APIRouter(prefix="/weather", tags=["weather"])

Lat = Annotated[float, Query(ge=-90, le=90)]
Lon = Annotated[float, Query(ge=-180, le=180)]


@router.get("/current", response_model=CurrentWeather)
async def current_weather(
    weather: WeatherDep, lat: Lat, lon: Lon, refresh: bool = False
) -> CurrentWeather:
    return await weather.get_current(lat, lon, force_refresh=refresh)


@router.get("/forecast", response_model=Forecast)
async def weather_forecast(
    weather: WeatherDep,
    lat: Lat,
    lon: Lon,
    hours: Annotated[int, Query(ge=3, le=120)] = 120,
    refresh: bool = False,
) -> Forecast:
    return await weather.get_forecast(lat, lon, horizon_hours=hours, force_refresh=refresh)


@router.get("/geocode", response_model=GeocodeResponse)
async def geocode(
    weather: WeatherDep,
    q: Annotated[str | None, Query(max_length=160)] = None,
    lat: Lat | None = None,
    lon: Lon | None = None,
    limit: Annotated[int, Query(ge=1, le=5)] = 5,
) -> GeocodeResponse:
    """Look up a place by name (q), or by coordinates (lat and lon). No match gives an empty list."""
    if q is not None:
        query = clean_text(q)
        if len(query) < 2:
            raise BadRequestError("Enter at least two characters to search for a place.")
        return GeocodeResponse(results=await weather.geocode(query, limit))
    if lat is None or lon is None:
        raise BadRequestError("Provide a place name, or both latitude and longitude.")
    return GeocodeResponse(results=await weather.reverse_geocode(lat, lon))
