"""Weather API success and failure, provenance, caching and invalid locations."""

import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.core.errors import WeatherError, WeatherNotConfiguredError
from app.schemas.weather import DataProvenance
from app.services.openweather import OpenWeatherClient, live_meta, parse_forecast
from app.services.weather import WeatherService
from tests.factories import owm_current, owm_forecast, owm_geocode

CURRENT_URL = "/data/2.5/weather"
FORECAST_URL = "/data/2.5/forecast"
PARAMS = {"lat": 30.9, "lon": 75.85}


class Clock:
    def __init__(self):
        self.now = datetime.now(UTC)

    def __call__(self):
        return self.now


@pytest.fixture
async def service(settings, session_factory):
    clock = Clock()
    async with httpx.AsyncClient() as http:
        yield (
            WeatherService(OpenWeatherClient(http, settings), session_factory, settings, clock),
            clock,
        )


async def test_success_is_live_and_validated(client, owm):
    owm.get(CURRENT_URL).respond(json=owm_current(temp=24.5, humidity=61, rain_1h=1.2))
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 200
    body = response.json()
    assert body["temperature_c"] == 24.5
    assert body["humidity_pct"] == 61
    assert body["rain_last_1h_mm"] == 1.2
    assert body["meta"]["provenance"] == "live"
    assert body["meta"]["source"] == "OpenWeatherMap"
    assert body["observed_at"]


async def test_unreported_rain_stays_unknown_rather_than_zero(client, owm):
    owm.get(CURRENT_URL).respond(json=owm_current())
    body = (await client.get("/api/weather/current", params=PARAMS)).json()
    assert body["rain_last_1h_mm"] is None


async def test_second_request_is_labelled_cached_not_live(client, owm):
    route = owm.get(CURRENT_URL).respond(json=owm_current())
    first = (await client.get("/api/weather/current", params=PARAMS)).json()
    second = (await client.get("/api/weather/current", params=PARAMS)).json()
    assert first["meta"]["provenance"] == "live"
    assert second["meta"]["provenance"] == "cached"
    assert route.call_count == 1


async def test_refresh_bypasses_the_cache(client, owm):
    route = owm.get(CURRENT_URL).respond(json=owm_current())
    await client.get("/api/weather/current", params=PARAMS)
    body = (await client.get("/api/weather/current", params={**PARAMS, "refresh": True})).json()
    assert body["meta"]["provenance"] == "live"
    assert route.call_count == 2


async def test_forecast_keeps_probability_and_amount_separate(client, owm):
    owm.get(FORECAST_URL).respond(json=owm_forecast(pop=0.8, rain_3h=2.5))
    body = (await client.get("/api/weather/forecast", params=PARAMS)).json()
    point = body["hourly"][0]
    assert point["rain_probability_pct"] == 80
    assert point["rain_mm"] == 2.5
    assert body["daily"]
    assert body["meta"]["provenance"] == "live"


async def test_forecast_period_with_no_rain_field_is_zero_amount(client, owm):
    owm.get(FORECAST_URL).respond(json=owm_forecast(pop=0.1))
    body = (await client.get("/api/weather/forecast", params=PARAMS)).json()
    assert body["hourly"][0]["rain_mm"] == 0


async def test_forecast_horizon_clips_periods(client, owm):
    owm.get(FORECAST_URL).respond(json=owm_forecast())
    body = (await client.get("/api/weather/forecast", params={**PARAMS, "hours": 24})).json()
    assert len(body["hourly"]) == 8
    assert body["horizon_hours"] == 24


async def test_failure_with_no_cache_is_an_error_never_mock_data(client, owm):
    route = owm.get(CURRENT_URL).respond(status_code=500)
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "weather_unavailable"
    assert "simulated" not in response.text.lower()
    assert route.call_count == 3  # the first attempt and two retries


async def test_timeouts_are_retried_then_reported(client, owm):
    route = owm.get(CURRENT_URL).mock(side_effect=httpx.ConnectTimeout("too slow"))
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 503
    assert route.call_count == 3


async def test_temporary_failure_recovers_through_retry(client, owm):
    owm.get(CURRENT_URL).mock(
        side_effect=[httpx.Response(503), httpx.Response(200, json=owm_current())]
    )
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 200
    assert response.json()["meta"]["provenance"] == "live"


async def test_bad_api_key_is_not_retried(client, owm):
    route = owm.get(CURRENT_URL).respond(status_code=401)
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "weather_auth_failed"
    assert route.call_count == 1


async def test_rate_limit_is_reported(client, owm):
    owm.get(CURRENT_URL).respond(status_code=429)
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.json()["error"]["code"] == "weather_rate_limited"


async def test_missing_key_explains_itself(make_client, make_settings, owm):
    client = await make_client(make_settings(openweather_api_key=None))
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "weather_not_configured"
    assert not owm.calls


async def test_provider_data_failing_validation_is_rejected(client, owm):
    owm.get(CURRENT_URL).respond(json=owm_current(humidity=400))
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "weather_data_invalid"


async def test_missing_fields_in_provider_data_are_rejected(client, owm):
    payload = owm_current()
    del payload["main"]["humidity"]
    owm.get(CURRENT_URL).respond(json=payload)
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.json()["error"]["code"] == "weather_data_invalid"


async def test_non_json_provider_response_is_rejected(client, owm):
    owm.get(CURRENT_URL).respond(text="<html>bad gateway</html>")
    response = await client.get("/api/weather/current", params=PARAMS)
    assert response.json()["error"]["code"] == "weather_data_invalid"


async def test_empty_forecast_is_rejected(client, owm):
    owm.get(FORECAST_URL).respond(json=owm_forecast(periods=0))
    response = await client.get("/api/weather/forecast", params=PARAMS)
    assert response.json()["error"]["code"] == "weather_data_invalid"


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 999, "lon": 75.85},
        {"lat": 30.9, "lon": -500},
        {"lat": "north", "lon": 75.85},
        {"lon": 75.85},
    ],
)
async def test_invalid_location_is_rejected_before_any_provider_call(client, owm, params):
    response = await client.get("/api/weather/current", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert not owm.calls


async def test_geocode_returns_matches(client, owm):
    owm.get("/geo/1.0/direct").respond(json=owm_geocode())
    body = (await client.get("/api/weather/geocode", params={"q": "Ludhiana"})).json()
    assert body["results"][0] == {
        "name": "Ludhiana",
        "state": "Punjab",
        "country": "IN",
        "latitude": 30.9,
        "longitude": 75.85,
        "timezone_offset_seconds": None,
    }


async def test_geocode_with_no_match_is_an_empty_list(client, owm):
    owm.get("/geo/1.0/direct").respond(json=[])
    response = await client.get("/api/weather/geocode", params={"q": "Nowhereville"})
    assert response.status_code == 200
    assert response.json()["results"] == []


async def test_reverse_geocode(client, owm):
    route = owm.get("/geo/1.0/reverse").respond(json=owm_geocode())
    body = (await client.get("/api/weather/geocode", params=PARAMS)).json()
    assert body["results"][0]["name"] == "Ludhiana"
    assert route.called


@pytest.mark.parametrize("params", [{}, {"q": "x"}, {"lat": 30.9}])
async def test_geocode_rejects_unusable_queries(client, params):
    assert (await client.get("/api/weather/geocode", params=params)).status_code == 400


async def test_api_key_never_reaches_a_client_response(client, owm):
    owm.get(CURRENT_URL).mock(side_effect=httpx.ConnectError("failed: appid=owm-test-secret"))
    response = await client.get("/api/weather/current", params=PARAMS)
    assert "owm-test-secret" not in response.text


async def test_expired_cache_is_served_flagged_when_the_provider_fails(service, owm):
    weather, clock = service
    route = owm.get(CURRENT_URL)
    route.respond(json=owm_current(observed=clock.now))
    await weather.get_current(30.9, 75.85)

    clock.now += timedelta(hours=1)
    route.respond(status_code=500)
    result = await weather.get_current(30.9, 75.85)
    assert result.meta.provenance == DataProvenance.CACHED
    assert result.meta.is_stale is True
    assert "could not be refreshed" in result.meta.warning


async def test_cache_too_old_to_trust_becomes_an_error(service, owm):
    weather, clock = service
    route = owm.get(CURRENT_URL)
    route.respond(json=owm_current(observed=clock.now))
    await weather.get_current(30.9, 75.85)

    clock.now += timedelta(hours=7)
    route.respond(status_code=500)
    with pytest.raises(WeatherError):
        await weather.get_current(30.9, 75.85)


async def test_missing_key_does_not_fall_back_to_cache(service, settings, session_factory, owm):
    weather, clock = service
    owm.get(CURRENT_URL).respond(json=owm_current(observed=clock.now))
    await weather.get_current(30.9, 75.85)
    clock.now += timedelta(hours=1)

    settings_without_key = settings.model_copy(update={"openweather_api_key": None})
    async with httpx.AsyncClient() as http:
        unconfigured = WeatherService(
            OpenWeatherClient(http, settings_without_key),
            session_factory,
            settings_without_key,
            clock,
        )
        with pytest.raises(WeatherNotConfiguredError):
            await unconfigured.get_current(30.9, 75.85)


async def test_old_observation_is_flagged_stale_even_when_fetched_live(service, owm):
    weather, clock = service
    owm.get(CURRENT_URL).respond(json=owm_current(observed=clock.now - timedelta(hours=5)))
    result = await weather.get_current(30.9, 75.85)
    assert result.meta.provenance == DataProvenance.LIVE
    assert result.meta.is_stale is True
    assert result.meta.warning


async def test_cached_forecast_drops_elapsed_periods(service, owm):
    weather, clock = service
    owm.get(FORECAST_URL).respond(json=owm_forecast(start=clock.now))
    first = await weather.get_forecast(30.9, 75.85)

    clock.now += timedelta(minutes=10)
    assert (await weather.get_forecast(30.9, 75.85)).meta.provenance == DataProvenance.CACHED

    clock.now += timedelta(hours=24)
    owm.get(FORECAST_URL).respond(status_code=500)
    with pytest.raises(WeatherError):
        await weather.get_forecast(30.9, 75.85)
    assert first.hourly


async def test_concurrent_requests_for_one_location_do_not_conflict(service, owm):
    weather, _ = service
    owm.get(CURRENT_URL).respond(json=owm_current())
    results = await asyncio.gather(*(weather.get_current(30.9, 75.85) for _ in range(5)))
    assert all(r.temperature_c == 24 for r in results)


def test_daily_summary_groups_by_the_location_timezone():
    # The first period is 18:00 UTC, or 23:30 in India. The next is 21:00 UTC, already tomorrow
    # there, though still today in UTC. So only local grouping gives this split of 1 and 7.
    start = datetime(2027, 1, 15, 15, 0, tzinfo=UTC)
    forecast = parse_forecast(owm_forecast(periods=8, start=start), live_meta(start))
    assert [(d.date.isoformat(), d.periods) for d in forecast.daily] == [
        ("2027-01-15", 1),
        ("2027-01-16", 7),
    ]
