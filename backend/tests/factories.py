"""Deterministic provider payloads and a scripted stand-in for the Anthropic client."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.intelligence.types import ForecastConditions, WeatherSnapshot
from app.schemas.weather import DataProvenance


def owm_current(
    temp=24.0,
    humidity=60,
    wind=2.0,
    rain_1h=None,
    lat=30.9,
    lon=75.85,
    observed=None,
    name="Ludhiana",
) -> dict:
    observed = observed or datetime.now(UTC)
    payload = {
        "coord": {"lat": lat, "lon": lon},
        "weather": [{"id": 800, "main": "Clear", "description": "clear sky", "icon": "01d"}],
        "main": {"temp": temp, "feels_like": temp - 1, "humidity": humidity, "pressure": 1012},
        "wind": {"speed": wind, "deg": 120},
        "clouds": {"all": 10},
        "dt": int(observed.timestamp()),
        "timezone": 19800,
        "name": name,
    }
    if rain_1h is not None:
        payload["rain"] = {"1h": rain_1h}
    return payload


def owm_forecast(
    periods=40, temp=24.0, humidity=60, wind=2.0, pop=0.1, rain_3h=None, start=None, temps=None
) -> dict:
    start = start or datetime.now(UTC)
    items = []
    for i in range(periods):
        moment = start + timedelta(hours=3 * (i + 1))
        item = {
            "dt": int(moment.timestamp()),
            "main": {
                "temp": temps[i] if temps else temp,
                "feels_like": temps[i] if temps else temp,
                "humidity": humidity,
            },
            "weather": [{"id": 500, "main": "Rain", "description": "light rain"}],
            "clouds": {"all": 40},
            "wind": {"speed": wind},
            "pop": pop,
        }
        if rain_3h is not None:
            item["rain"] = {"3h": rain_3h}
        items.append(item)
    return {
        "list": items,
        "city": {"name": "Ludhiana", "coord": {"lat": 30.9, "lon": 75.85}, "timezone": 19800},
    }


def owm_geocode() -> list[dict]:
    return [{"name": "Ludhiana", "lat": 30.9, "lon": 75.85, "country": "IN", "state": "Punjab"}]


def snapshot(**overrides) -> WeatherSnapshot:
    """Live, complete and unremarkable weather, for tests to vary one thing at a time."""
    values = {
        "provenance": DataProvenance.LIVE,
        "source": "OpenWeatherMap",
        "observed_at": datetime(2027, 1, 15, 6, 0, tzinfo=UTC),
        "temperature_c": 20.0,
        "humidity_pct": 55.0,
        "wind_speed_ms": 2.0,
        "description": "clear sky",
        "forecast_available": True,
        "rain_next_24h_mm": 0.0,
        "rain_next_48h_mm": 0.0,
        "rain_prob_max_24h_pct": 10.0,
        "rain_prob_max_48h_pct": 10.0,
        "temp_max_48h_c": 20.0,
        "temp_min_48h_c": 10.0,
        "humidity_mean_48h_pct": 55.0,
        "wind_max_24h_ms": 2.0,
    }
    values.update(overrides)
    return WeatherSnapshot(**values)


def period(temp, humidity, rain=0.0) -> ForecastConditions:
    return ForecastConditions(temperature_c=temp, humidity_pct=humidity, rain_mm=rain)


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def tool_block(name: str, tool_input: dict, block_id: str = "toolu_1") -> SimpleNamespace:
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=tool_input)


def model_response(stop_reason: str, *blocks) -> SimpleNamespace:
    usage = SimpleNamespace(
        input_tokens=1, cache_creation_input_tokens=0, cache_read_input_tokens=0, output_tokens=1
    )
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks), usage=usage)


def final_json(**overrides) -> str:
    import json

    payload = {
        "intent": "general",
        "recommendation": None,
        "summary": "Hello.",
        "reasoning": [],
        "risk_level": "not_applicable",
        "confidence": "not_applicable",
        "missing_information": [],
        "next_steps": [],
        "requires_expert_verification": False,
    }
    payload.update(overrides)
    return json.dumps(payload)


def final_response(**overrides) -> SimpleNamespace:
    return model_response("end_turn", text_block(final_json(**overrides)))


class FakeAnthropic:
    """Plays back a script of responses or exceptions, and records every request it receives."""

    def __init__(self, script=None, repeat=None):
        self.script = list(script or [])
        self.repeat = repeat
        self.calls: list[dict] = []
        self.messages = self

    async def create(self, **params):
        recorded = dict(params)
        recorded["messages"] = copy.copy(params["messages"])
        self.calls.append(recorded)
        item = self.script.pop(0) if self.script else self.repeat
        if item is None:
            raise AssertionError("The fake model ran out of scripted responses.")
        if isinstance(item, BaseException):
            raise item
        return item

    async def close(self):
        return None
