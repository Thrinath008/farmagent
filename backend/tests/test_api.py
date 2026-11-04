"""REST endpoints, ownership, persistence through the API, security and scenarios."""

import json
import uuid
from datetime import UTC, date, datetime

import anthropic
import httpx2
import pytest
from sqlalchemy import func, select

from app.api.agent import message_requests_save
from app.core.middleware import SlidingWindowLimiter
from app.models import Conversation, Farm, FarmCrop, Message, Recommendation, User, WeatherCache
from tests.factories import (
    FakeAnthropic,
    final_response,
    model_response,
    owm_current,
    owm_forecast,
    tool_block,
)

FARM = {
    "name": "Home field",
    "location_name": "Ludhiana",
    "state": "Punjab",
    "country": "IN",
    "latitude": 30.9,
    "longitude": 75.85,
    "size_value": 5,
    "area_unit": "acre",
    "soil_type": "loam",
    "crops": [
        {
            "crop": "wheat",
            "variety": "PBW 826",
            "sowing_date": "2026-11-10",
            "growth_stage": "tillering",
            "irrigation_method": "flood",
        }
    ],
}
ADVICE = dict(
    intent="irrigation_advice",
    recommendation="Consider postponing irrigation.",
    summary="Rain is forecast.",
    risk_level="moderate",
    confidence="limited",
)
LUDHIANA = {"latitude": 30.9, "longitude": 75.85}


@pytest.fixture
def weather_api(owm):
    owm.get("/data/2.5/weather").respond(json=owm_current(temp=24, humidity=80))
    owm.get("/data/2.5/forecast").respond(json=owm_forecast(pop=0.85, rain_3h=2.0, humidity=80))
    return owm


async def make_farm(client, headers, **overrides) -> dict:
    response = await client.post("/api/farms", json={**FARM, **overrides}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def other_guest(client) -> dict:
    return {"X-Guest-Token": (await client.post("/api/session/guest")).json()["token"]}


# Health and configuration


async def test_health_reports_state_without_secrets(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["weather_configured"] is True
    assert body["ai_configured"] is True
    assert body["ai_model"] == "claude-test-model"
    assert "secret" not in response.text


async def test_health_is_degraded_when_the_database_is_down(make_client, make_settings):
    settings = make_settings(database_url="sqlite+aiosqlite:////nonexistent-dir/none.db")
    client = await make_client(settings)
    body = (await client.get("/api/health")).json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"


async def test_database_outage_on_a_route_is_a_safe_error(make_client, make_settings):
    settings = make_settings(database_url="sqlite+aiosqlite:////nonexistent-dir/none.db")
    client = await make_client(settings)
    response = await client.post("/api/session/guest")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert "nonexistent" not in response.text


def test_plain_postgres_urls_are_normalized(make_settings):
    url = make_settings(database_url="postgres://u:p@host:5432/db").database_url
    assert url == "postgresql+psycopg://u:p@host:5432/db"
    url = make_settings(database_url="postgresql://u:p@host/db").database_url
    assert url == "postgresql+psycopg://u:p@host/db"


def test_blank_secrets_count_as_missing(make_settings):
    settings = make_settings(openweather_api_key="  ", anthropic_api_key="")
    assert settings.weather_configured is False
    assert settings.ai_configured is False


def test_secrets_do_not_appear_in_settings_repr(settings):
    assert "owm-test-secret" not in repr(settings)
    assert "anthropic-test-secret" not in repr(settings)


# Security


async def test_cors_allows_the_frontend_only(client):
    allowed = await client.get("/api/health", headers={"Origin": "https://farmagent.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://farmagent.example"
    blocked = await client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in blocked.headers


async def test_rate_limit_returns_429_with_retry_after_and_cors(make_client, make_settings, owm):
    client = await make_client(
        make_settings(rate_limit_enabled=True, rate_limit_default_per_minute=2)
    )
    owm.get("/data/2.5/weather").respond(json=owm_current())
    headers = {"Origin": "https://farmagent.example"}
    params = {"lat": 30.9, "lon": 75.85}
    for _ in range(2):
        assert (await client.get("/api/weather/current", params=params)).status_code == 200
    limited = await client.get("/api/weather/current", params=params, headers=headers)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["access-control-allow-origin"] == "https://farmagent.example"


async def test_agent_routes_have_a_stricter_limit(make_client, make_settings):
    client = await make_client(
        make_settings(rate_limit_enabled=True, rate_limit_agent_per_minute=1)
    )
    assert (await client.get("/api/scenarios")).status_code == 200
    assert (await client.get("/api/scenarios")).status_code == 429
    assert (await client.get("/api/crops")).status_code == 200


async def test_health_is_never_rate_limited(make_client, make_settings):
    client = await make_client(
        make_settings(rate_limit_enabled=True, rate_limit_default_per_minute=1)
    )
    for _ in range(3):
        assert (await client.get("/api/health")).status_code == 200


def test_sliding_window_recovers_after_the_window():
    moment = [0.0]
    limiter = SlidingWindowLimiter(clock=lambda: moment[0], window=60)
    assert limiter.check("k", 1) is None
    assert limiter.check("k", 1) == pytest.approx(60)
    assert limiter.check("other", 1) is None
    moment[0] = 61
    assert limiter.check("k", 1) is None


async def test_unhandled_errors_do_not_leak_internals(make_client, settings):
    class Exploding(FakeAnthropic):
        async def create(self, **params):
            raise RuntimeError("database password is hunter2")

    client = await make_client(settings, model=Exploding(), raise_app_exceptions=False)
    headers = {"X-Guest-Token": (await client.post("/api/session/guest")).json()["token"]}
    response = await client.post(
        "/api/agent/chat",
        json={"message": "hello"},
        headers={**headers, "Origin": "https://farmagent.example"},
    )
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    # The browser has to be able to read this error, so CORS headers must survive it.
    assert response.headers["access-control-allow-origin"] == "https://farmagent.example"
    assert response.headers["x-request-id"]


async def test_validation_errors_do_not_echo_input(client, guest):
    response = await client.post(
        "/api/farms", json={"latitude": "secret-value-xyz", "longitude": 1}, headers=guest
    )
    assert response.status_code == 422
    assert "secret-value-xyz" not in response.text
    assert response.json()["error"]["fields"]


async def test_control_characters_are_stripped_from_messages(client, guest, fake_model):
    fake_model.script.append(final_response(intent="general", summary="Hi."))
    response = await client.post(
        "/api/agent/chat", json={"message": "he\x00llo\x07 there"}, headers=guest
    )
    assert response.status_code == 200
    assert fake_model.calls[0]["messages"][-1]["content"] == "hello there"


# Sessions


async def test_guest_token_is_stored_only_as_a_hash(client, session_factory):
    response = await client.post("/api/session/guest")
    token = response.json()["token"]
    assert len(token) >= 40
    async with session_factory() as session:
        user = await session.scalar(select(User))
    assert token not in user.guest_token_hash
    assert len(user.guest_token_hash) == 64


@pytest.mark.parametrize(
    "request_args",
    [
        ("GET", "/api/farms"),
        ("GET", "/api/session/me"),
        ("GET", "/api/recommendations"),
        ("GET", "/api/conversations"),
        ("POST", "/api/agent/chat"),
        ("POST", "/api/irrigation/assess"),
    ],
)
async def test_routes_require_a_session(client, request_args):
    method, path = request_args
    response = await client.request(method, path, json={"message": "hi"})
    assert response.status_code in (401, 422)
    bad = await client.request(
        method, path, json={"message": "hi"}, headers={"X-Guest-Token": "nope"}
    )
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "unauthorized"


async def test_profile_update(client, guest):
    response = await client.patch(
        "/api/session/me",
        json={"display_name": "Harpreet", "preferred_language": "Punjabi"},
        headers=guest,
    )
    assert response.json()["display_name"] == "Harpreet"
    assert (await client.get("/api/session/me", headers=guest)).json()[
        "preferred_language"
    ] == "Punjabi"


async def test_deleting_a_guest_removes_all_their_data(client, guest, session_factory, fake_model):
    await make_farm(client, guest)
    fake_model.script.append(final_response(intent="general", summary="Hi."))
    await client.post("/api/agent/chat", json={"message": "hello"}, headers=guest)

    assert (await client.delete("/api/session/me", headers=guest)).status_code == 204
    assert (await client.get("/api/session/me", headers=guest)).status_code == 401
    async with session_factory() as session:
        for model in (User, Farm, FarmCrop, Conversation, Message):
            assert await session.scalar(select(func.count()).select_from(model)) == 0


# Farms


async def test_farm_create_read_update_delete(client, guest):
    farm = await make_farm(client, guest)
    assert farm["crops"][0]["crop_name"] == "Wheat"
    assert farm["crops"][0]["support_level"] == "rules_implemented"
    assert farm["crops"][0]["growth_stage_label"] == "Tillering"
    assert farm["crops"][0]["irrigation_schedule"]["windows"][0]["number"] == 1

    assert len((await client.get("/api/farms", headers=guest)).json()) == 1

    updated = await client.patch(
        f"/api/farms/{farm['id']}", json={"soil_type": "clay", "name": "North field"}, headers=guest
    )
    assert updated.json()["soil_type"] == "clay"
    assert updated.json()["name"] == "North field"
    assert updated.json()["location_name"] == "Ludhiana"

    assert (await client.delete(f"/api/farms/{farm['id']}", headers=guest)).status_code == 204
    assert (await client.get(f"/api/farms/{farm['id']}", headers=guest)).status_code == 404


async def test_multiple_farms_and_crops(client, guest):
    first = await make_farm(client, guest)
    await make_farm(client, guest, name="Second", crops=[])
    assert len((await client.get("/api/farms", headers=guest)).json()) == 2

    added = await client.post(
        f"/api/farms/{first['id']}/crops",
        json={"crop": "rice", "growth_stage": "transplanting"},
        headers=guest,
    )
    assert added.status_code == 201
    assert added.json()["support_level"] == "planned"
    assert len((await client.get(f"/api/farms/{first['id']}", headers=guest)).json()["crops"]) == 2


async def test_growth_stage_update_normalizes_and_validates(client, guest):
    farm = await make_farm(client, guest)
    crop_id = farm["crops"][0]["id"]
    url = f"/api/farms/{farm['id']}/crops/{crop_id}"
    good = await client.patch(url, json={"growth_stage": "Flowering"}, headers=guest)
    assert good.json()["growth_stage"] == "heading_flowering"
    bad = await client.patch(url, json={"growth_stage": "purple"}, headers=guest)
    assert bad.status_code == 400
    assert (await client.delete(url, headers=guest)).status_code == 204
    assert (await client.patch(url, json={}, headers=guest)).status_code == 404


async def test_farm_with_nothing_filled_in_stays_empty(client, guest):
    farm = await make_farm(
        client,
        guest,
        name=None,
        location_name=None,
        state=None,
        country=None,
        latitude=None,
        longitude=None,
        size_value=None,
        area_unit=None,
        soil_type=None,
        crops=[],
    )
    for field in ("name", "soil_type", "latitude", "size_value"):
        assert farm[field] is None


@pytest.mark.parametrize(
    "bad",
    [
        {"latitude": 30.9},
        {"longitude": 75},
        {"latitude": 999, "longitude": 75},
        {"size_value": -1},
        {"area_unit": "furlong"},
        {"soil_type": "marshmallow"},
        {"unexpected_field": 1},
        {"crops": [{"crop": "dragonfruit"}]},
        {"crops": [{"crop": "wheat", "growth_stage": "purple"}]},
    ],
)
async def test_invalid_farms_are_rejected(client, guest, bad):
    response = await client.post("/api/farms", json=bad, headers=guest)
    assert response.status_code == 422


async def test_one_guest_cannot_touch_another_guests_data(client, guest, fake_model):
    farm = await make_farm(client, guest)
    fake_model.script.append(final_response(intent="general", summary="Hi."))
    chat = await client.post("/api/agent/chat", json={"message": "hello"}, headers=guest)
    conversation_id = chat.json()["conversation_id"]
    saved = await client.post(
        "/api/recommendations",
        json={"origin": "assistant", "advice": {"intent": "general", "summary": "x"}},
        headers=guest,
    )
    recommendation_id = saved.json()["id"]

    intruder = await other_guest(client)
    assert (await client.get("/api/farms", headers=intruder)).json() == []
    assert (await client.get(f"/api/farms/{farm['id']}", headers=intruder)).status_code == 404
    assert (await client.delete(f"/api/farms/{farm['id']}", headers=intruder)).status_code == 404
    assert (
        await client.patch(f"/api/farms/{farm['id']}", json={"name": "x"}, headers=intruder)
    ).status_code == 404
    assert (
        await client.post(f"/api/farms/{farm['id']}/crops", json={"crop": "rice"}, headers=intruder)
    ).status_code == 404
    assert (
        await client.get(f"/api/conversations/{conversation_id}", headers=intruder)
    ).status_code == 404
    assert (
        await client.delete(f"/api/conversations/{conversation_id}", headers=intruder)
    ).status_code == 404
    assert (await client.get("/api/recommendations", headers=intruder)).json() == []
    assert (
        await client.delete(f"/api/recommendations/{recommendation_id}", headers=intruder)
    ).status_code == 404
    assert (
        await client.post(
            "/api/agent/chat",
            json={"message": "hi", "conversation_id": conversation_id},
            headers=intruder,
        )
    ).status_code == 404
    assert (
        await client.post(
            "/api/agent/chat", json={"message": "hi", "farm_id": farm["id"]}, headers=intruder
        )
    ).status_code == 404
    assert (
        await client.post("/api/irrigation/assess", json={"farm_id": farm["id"]}, headers=intruder)
    ).status_code == 404
    assert (
        await client.post(
            "/api/recommendations",
            json={
                "origin": "assistant",
                "farm_id": farm["id"],
                "advice": {"intent": "general", "summary": "x"},
            },
            headers=intruder,
        )
    ).status_code == 404


# Catalogue


async def test_catalogue_is_honest_about_support(client):
    body = (await client.get("/api/crops")).json()
    support = {crop["id"]: crop["support_level"] for crop in body["crops"]}
    assert support["wheat"] == "rules_implemented"
    for crop in ("rice", "maize", "cotton", "sugarcane", "pulses", "vegetables"):
        assert support[crop] == "planned"
    wheat = next(crop for crop in body["crops"] if crop["id"] == "wheat")
    assert {s["id"] for s in wheat["stages"]} >= {"vegetative", "crown_root_initiation", "maturity"}
    assert wheat["sources"]
    assert "unknown" not in body["soil_types"]


# Assessments


async def test_irrigation_assessment_for_a_farm(client, guest, weather_api):
    farm = await make_farm(client, guest)
    response = await client.post(
        "/api/irrigation/assess",
        json={
            "farm_id": farm["id"],
            "farm_crop_id": farm["crops"][0]["id"],
            "soil_moisture": "adequate",
        },
        headers=guest,
    )
    assert response.status_code == 200
    body = response.json()
    assessment = body["assessment"]
    assert assessment["crop"] == "wheat"
    assert assessment["growth_stage"] == "tillering"
    assert assessment["weather_provenance"] == "live"
    assert assessment["status"] == "caution"  # 32 mm is forecast at an 85% chance
    assert assessment["schedule"] is not None
    assert body["weather"]["temperature_c"] == 24
    assert body["advice"]["weather_context"]["provenance"] == "live"
    assert body["weather_issues"] == []


async def test_stated_values_override_what_is_stored_on_the_farm(client, guest, weather_api):
    farm = await make_farm(client, guest)
    body = (
        await client.post(
            "/api/irrigation/assess",
            json={
                "farm_id": farm["id"],
                "farm_crop_id": farm["crops"][0]["id"],
                "growth_stage": "maturity",
                "soil_type": "sandy",
            },
            headers=guest,
        )
    ).json()
    assert body["assessment"]["growth_stage"] == "maturity"
    soil = next(f for f in body["assessment"]["factors"] if f["key"] == "soil_type")
    assert soil["value"] == "Sandy"


async def test_weather_failure_gives_an_honest_assessment_not_a_crash(client, guest, owm):
    owm.get("/data/2.5/weather").respond(status_code=500)
    owm.get("/data/2.5/forecast").respond(status_code=500)
    response = await client.post(
        "/api/irrigation/assess", json={"latitude": 30.9, "longitude": 75.85}, headers=guest
    )
    assert response.status_code == 200
    body = response.json()
    assert body["assessment"]["status"] == "insufficient_information"
    assert body["advice"]["recommendation"] is None
    assert body["weather"] is None
    assert body["weather_issues"][0]["code"] == "weather_unavailable"


async def test_both_feeds_failing_the_same_way_report_it_once(client, guest, owm):
    owm.get("/data/2.5/weather").respond(status_code=500)
    owm.get("/data/2.5/forecast").respond(status_code=500)
    body = (
        await client.post(
            "/api/irrigation/assess", json={"latitude": 30.9, "longitude": 75.85}, headers=guest
        )
    ).json()
    assert [issue["code"] for issue in body["weather_issues"]] == ["weather_unavailable"]


async def test_feeds_failing_differently_report_both(client, guest, owm):
    owm.get("/data/2.5/weather").respond(status_code=500)
    owm.get("/data/2.5/forecast").respond(status_code=429)
    body = (
        await client.post(
            "/api/irrigation/assess", json={"latitude": 30.9, "longitude": 75.85}, headers=guest
        )
    ).json()
    assert {issue["code"] for issue in body["weather_issues"]} == {
        "weather_unavailable",
        "weather_rate_limited",
    }


async def test_one_failed_weather_feed_is_stated_as_missing(client, guest, owm):
    owm.get("/data/2.5/weather").respond(json=owm_current())
    owm.get("/data/2.5/forecast").respond(status_code=500)
    body = (
        await client.post(
            "/api/irrigation/assess",
            json={"latitude": 30.9, "longitude": 75.85, "soil_moisture": "low"},
            headers=guest,
        )
    ).json()
    assert body["assessment"]["status"] != "favorable"
    assert "Forecast rainfall amount" in body["assessment"]["missing_information"]
    assert body["weather_issues"]


async def test_assessment_without_any_location_says_so(client, guest, owm):
    body = (await client.post("/api/irrigation/assess", json={}, headers=guest)).json()
    assert body["assessment"]["status"] == "insufficient_information"
    assert body["weather_issues"][0]["code"] == "location_missing"
    assert not owm.calls


async def test_half_a_coordinate_is_rejected(client, guest):
    response = await client.post("/api/irrigation/assess", json={"latitude": 30.9}, headers=guest)
    assert response.status_code == 422


async def test_pest_risk_assessment(client, guest, weather_api):
    farm = await make_farm(client, guest)
    response = await client.post(
        "/api/pest-risk/assess",
        json={"farm_id": farm["id"], "farm_crop_id": farm["crops"][0]["id"]},
        headers=guest,
    )
    assert response.status_code == 200
    assessment = response.json()["assessment"]
    assert assessment["risks"]
    assert "not a plant disease diagnosis" in assessment["disclaimer"]
    assert assessment["weather_provenance"] == "live"
    assert assessment["growth_stage_label"] == "Tillering"


async def test_pest_risk_for_a_crop_without_rules(client, guest, weather_api):
    body = (
        await client.post(
            "/api/pest-risk/assess",
            json={"latitude": 30.9, "longitude": 75.85, "crop": "cotton"},
            headers=guest,
        )
    ).json()
    assert body["assessment"]["risks"] == []
    assert "not implemented" in body["assessment"]["explanation"]


# Chat


async def test_chat_persists_the_exchange_and_reuses_history(
    client, guest, fake_model, weather_api
):
    farm = await make_farm(client, guest)
    fake_model.script.extend(
        [
            model_response(
                "tool_use", tool_block("assess_irrigation_need", {**LUDHIANA, "crop": "wheat"})
            ),
            final_response(**ADVICE),
            final_response(intent="general", summary="You are welcome."),
        ]
    )
    first = await client.post(
        "/api/agent/chat",
        json={"message": "Should I irrigate my wheat field today?", "farm_id": farm["id"]},
        headers=guest,
    )
    assert first.status_code == 200
    body = first.json()
    assert body["advice"]["recommendation"] == ADVICE["recommendation"]
    assert body["advice"]["weather_context"]["provenance"] == "live"
    assert body["tool_log"][0]["name"] == "assess_irrigation_need"

    # Stored farm details reach the model, so the farmer need not repeat them.
    context_text = fake_model.calls[0]["system"][1]["text"]
    assert "Ludhiana" in context_text
    assert "tillering" in context_text

    conversation_id = body["conversation_id"]
    second = await client.post(
        "/api/agent/chat",
        json={"message": "Thanks", "conversation_id": conversation_id},
        headers=guest,
    )
    assert second.status_code == 200
    sent = fake_model.calls[2]["messages"]
    assert sent[0] == {"role": "user", "content": "Should I irrigate my wheat field today?"}
    assert sent[1]["role"] == "assistant"
    assert "Consider postponing" in sent[1]["content"]
    assert sent[2] == {"role": "user", "content": "Thanks"}
    # The conversation keeps its farm without the client resending it.
    assert "Ludhiana" in fake_model.calls[2]["system"][1]["text"]

    detail = (await client.get(f"/api/conversations/{conversation_id}", headers=guest)).json()
    assert detail["title"].startswith("Should I irrigate")
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant", "user", "assistant"]
    assert detail["messages"][1]["advice"]["intent"] == "irrigation_advice"
    assert detail["messages"][1]["tool_log"][0]["ok"] is True


async def test_claude_failure_stores_nothing_and_returns_a_safe_error(
    client, guest, fake_model, session_factory
):
    fake_model.script.append(
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid"))
    )
    response = await client.post("/api/agent/chat", json={"message": "hello"}, headers=guest)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "agent_unavailable"
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == 0
        assert await session.scalar(select(func.count()).select_from(Conversation)) == 0


async def test_chat_without_credentials_explains_itself(make_client, make_settings):
    settings = make_settings(anthropic_api_key=None)
    client = await make_client(settings, model=None)
    headers = {"X-Guest-Token": (await client.post("/api/session/guest")).json()["token"]}
    for path in ("/api/agent/chat", "/api/agent/chat/stream"):
        response = await client.post(path, json={"message": "hello"}, headers=headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "agent_not_configured"


async def test_overlong_messages_are_refused_before_reaching_the_model(
    make_client, make_settings, fake_model
):
    client = await make_client(make_settings(agent_max_message_chars=100))
    headers = {"X-Guest-Token": (await client.post("/api/session/guest")).json()["token"]}
    response = await client.post("/api/agent/chat", json={"message": "x" * 101}, headers=headers)
    assert response.status_code == 400
    assert fake_model.calls == []


@pytest.mark.parametrize("message", ["", "   ", "\x00\x01"])
async def test_empty_messages_are_refused(client, guest, message):
    response = await client.post("/api/agent/chat", json={"message": message}, headers=guest)
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Save this recommendation", True),
        ("please record that for me", True),
        ("इसे सेव करो", True),
        ("Should I irrigate?", False),
        ("will this rain save me an irrigation", True),
        ("What is the risk of lodging?", False),
    ],
)
def test_save_requests_are_recognised(message, expected):
    assert message_requests_save(message) is expected


async def test_chat_only_saves_when_asked(client, guest, fake_model, weather_api, session_factory):
    save_call = tool_block(
        "save_recommendation",
        {"intent": "irrigation_advice", "recommendation": "Wait.", "summary": "Rain."},
    )
    fake_model.script.extend(
        [
            model_response("tool_use", save_call),
            final_response(intent="general", summary="Shall I save it?"),
            model_response("tool_use", save_call),
            final_response(intent="general", summary="Saved."),
        ]
    )
    unasked = await client.post(
        "/api/agent/chat", json={"message": "Should I wait?"}, headers=guest
    )
    assert unasked.json()["saved_recommendation_ids"] == []

    asked = await client.post(
        "/api/agent/chat",
        json={"message": "Yes, save it", "conversation_id": unasked.json()["conversation_id"]},
        headers=guest,
    )
    assert len(asked.json()["saved_recommendation_ids"]) == 1
    async with session_factory() as session:
        record = await session.scalar(select(Recommendation))
    assert str(record.conversation_id) == unasked.json()["conversation_id"]


def parse_stream(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


async def test_stream_reports_tools_then_the_final_answer(client, guest, fake_model, weather_api):
    fake_model.script.extend(
        [
            model_response("tool_use", tool_block("get_current_weather", LUDHIANA)),
            final_response(**ADVICE),
        ]
    )
    response = await client.post(
        "/api/agent/chat/stream", json={"message": "Should I irrigate?"}, headers=guest
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_stream(response.text)
    assert [e["type"] for e in events] == ["status", "tool_start", "tool_end", "status", "final"]
    assert events[1]["name"] == "get_current_weather"
    final = events[-1]["response"]
    assert final["advice"]["recommendation"] == ADVICE["recommendation"]
    detail = await client.get(f"/api/conversations/{final['conversation_id']}", headers=guest)
    assert len(detail.json()["messages"]) == 2


async def test_stream_reports_failure_as_an_error_event(client, guest, fake_model):
    fake_model.script.append(
        anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x.invalid"))
    )
    response = await client.post("/api/agent/chat/stream", json={"message": "hi"}, headers=guest)
    assert response.status_code == 200
    events = parse_stream(response.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["code"] == "agent_unavailable"


async def test_analyze_returns_a_briefing_without_saving(
    client, guest, fake_model, weather_api, session_factory
):
    farm = await make_farm(client, guest)
    fake_model.script.extend(
        [
            model_response(
                "tool_use", tool_block("assess_irrigation_need", {**LUDHIANA, "crop": "wheat"})
            ),
            final_response(**{**ADVICE, "intent": "farm_briefing"}),
        ]
    )
    response = await client.post(
        "/api/agent/analyze",
        json={"farm_id": farm["id"], "farm_crop_id": farm["crops"][0]["id"]},
        headers=guest,
    )
    assert response.status_code == 200
    assert response.json()["advice"]["weather_context"]["provenance"] == "live"
    assert "Focus on my wheat" in fake_model.calls[0]["messages"][-1]["content"]
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == 0
        assert await session.scalar(select(func.count()).select_from(Recommendation)) == 0


# Conversations


async def test_conversation_list_create_delete(client, guest):
    created = await client.post(
        "/api/conversations", json={"title": "Season planning"}, headers=guest
    )
    assert created.status_code == 201
    conversation_id = created.json()["id"]
    listed = (await client.get("/api/conversations", headers=guest)).json()
    assert listed[0]["title"] == "Season planning"
    empty = (await client.get(f"/api/conversations/{conversation_id}", headers=guest)).json()
    assert empty["messages"] == []
    assert (
        await client.delete(f"/api/conversations/{conversation_id}", headers=guest)
    ).status_code == 204
    assert (await client.get("/api/conversations", headers=guest)).json() == []


# Recommendations


async def test_recommendation_create_list_delete(client, guest):
    farm = await make_farm(client, guest)
    payload = {
        "origin": "irrigation_advisor",
        "farm_id": farm["id"],
        "crop": "wheat",
        "latitude": 30.9,
        "longitude": 75.85,
        "advice": {
            "intent": "irrigation_advice",
            "recommendation": "Wait.",
            "summary": "Rain is forecast.",
            "risk_level": "moderate",
            "confidence": "limited",
            "weather_context": {
                "provenance": "live",
                "source": "OpenWeatherMap",
                "observed_at": "2027-01-15T06:00:00Z",
                "temperature_c": 24,
            },
        },
    }
    created = await client.post("/api/recommendations", json=payload, headers=guest)
    assert created.status_code == 201
    record = created.json()
    assert record["weather_provenance"] == "live"
    assert record["weather_observed_at"].startswith("2027-01-15T06:00:00")
    assert record["advice"]["weather_context"]["temperature_c"] == 24

    assert len((await client.get("/api/recommendations", headers=guest)).json()) == 1
    by_farm = await client.get(
        "/api/recommendations", params={"farm_id": farm["id"]}, headers=guest
    )
    assert len(by_farm.json()) == 1
    other = await client.get("/api/recommendations", params={"intent": "general"}, headers=guest)
    assert other.json() == []

    deleted = await client.delete(f"/api/recommendations/{record['id']}", headers=guest)
    assert deleted.status_code == 204
    assert (await client.get("/api/recommendations", headers=guest)).json() == []
    missing = await client.delete(f"/api/recommendations/{uuid.uuid4()}", headers=guest)
    assert missing.status_code == 404


async def test_oversized_recommendation_is_refused(client, guest):
    response = await client.post(
        "/api/recommendations",
        json={"origin": "assistant", "advice": {"intent": "general", "summary": "x" * 30_000}},
        headers=guest,
    )
    assert response.status_code == 422


# Scenario Lab


async def test_scenario_definitions_match_the_spec(client):
    scenarios = {s["id"]: s for s in (await client.get("/api/scenarios")).json()}
    a, b = scenarios["A"]["inputs"], scenarios["B"]["inputs"]
    assert (
        a["temperature_c"],
        a["humidity_pct"],
        a["rain_probability_pct"],
        a["expected_rain_mm"],
    ) == (24, 80, 85, 15)
    assert (
        b["temperature_c"],
        b["humidity_pct"],
        b["rain_probability_pct"],
        b["expected_rain_mm"],
    ) == (36, 30, 5, 0)
    assert a["crop"] == b["crop"] == "wheat"
    assert a["growth_stage"] == b["growth_stage"] == "vegetative"
    assert a["soil_moisture"] == "unknown"
    assert b["soil_moisture"] == "low"


async def test_both_scenarios_differ_and_explain_why(client, owm):
    response = await client.post("/api/scenarios/run", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["label"] == "SIMULATED DATA"
    assert body["outcomes_differ"] is True
    a, b = body["results"]

    assert a["provenance"] == b["provenance"] == "simulated"
    assert a["assessment"]["status"] == "caution"
    assert a["assessment"]["action"] == "consider_postponing"
    assert b["assessment"]["status"] == "favorable"
    assert b["assessment"]["action"] == "consider_irrigating"

    assert "soil moisture" in a["assessment"]["summary"]
    assert "how much rain actually falls" in a["assessment"]["summary"]
    assert "Current soil moisture" in a["assessment"]["missing_information"]
    assert a["assessment"]["confidence"] == "limited"
    assert b["assessment"]["confidence"] == "moderate"
    assert a["assessment"]["score"] < 0 < b["assessment"]["score"]

    for result in (a, b):
        assert result["assessment"]["weather_provenance"] == "simulated"
        assert result["advice"]["weather_context"]["provenance"] == "simulated"
        assert result["advice"]["data_sources"][0] == "Simulated (Scenario Lab)"
        assert any("simulated" in line for line in result["assessment"]["limitations"])

    # The lab needs no live weather at all.
    assert not owm.calls


async def test_scenario_comparison_lays_out_the_differences(client):
    body = (await client.post("/api/scenarios/run", json={})).json()
    inputs = {row["key"]: row for row in body["input_differences"]}
    assert inputs["temperature_c"]["values"] == {"A": "24 °C", "B": "36 °C"}
    assert inputs["temperature_c"]["differs"] is True
    assert inputs["soil_moisture"]["values"] == {"A": "Not provided", "B": "Low"}
    assert inputs["crop"]["differs"] is False

    factors = {row["key"]: row for row in body["factor_comparison"]}
    assert factors["forecast_rain"]["weights"]["A"] < 0 < factors["forecast_rain"]["weights"]["B"]
    assert factors["soil_moisture"]["weights"] == {"A": 0, "B": 3}
    assert (
        factors["water_demand"]["explanations"]["A"] != factors["water_demand"]["explanations"]["B"]
    )


async def test_scenarios_are_deterministic(client):
    first = (await client.post("/api/scenarios/run", json={})).json()
    second = (await client.post("/api/scenarios/run", json={})).json()
    assert first == second


async def test_a_single_scenario_can_be_run(client):
    body = (await client.post("/api/scenarios/run", json={"scenario_ids": ["B"]})).json()
    assert [r["definition"]["id"] for r in body["results"]] == ["B"]
    assert body["outcomes_differ"] is False


@pytest.mark.parametrize("ids", [["C"], []])
async def test_unknown_scenarios_are_rejected(client, ids):
    response = await client.post("/api/scenarios/run", json={"scenario_ids": ids})
    assert response.status_code == 422


class ToolThenAnswerModel(FakeAnthropic):
    """Answers by conversation state, since the two scenario runs share one client concurrently."""

    async def create(self, **params):
        self.calls.append(dict(params))
        if isinstance(params["messages"][-1]["content"], str):
            return model_response(
                "tool_use", tool_block("assess_irrigation_need", {**LUDHIANA, "crop": "wheat"})
            )
        return final_response(**ADVICE)


async def test_scenarios_with_ai_use_the_agent_on_simulated_data(make_client, settings):
    model = ToolThenAnswerModel()
    client = await make_client(settings, model=model)
    body = (await client.post("/api/scenarios/run", json={"include_ai": True})).json()
    for result in body["results"]:
        ai = result["ai"]
        assert ai["status"] == "completed"
        assert ai["advice"]["weather_context"]["provenance"] == "simulated"
        assert ai["tool_log"][0]["provenance"] == "simulated"
    assert len(model.calls) == 4
    assert "SIMULATED" in model.calls[0]["system"][1]["text"]


async def test_scenarios_survive_the_ai_being_unavailable(make_client, make_settings):
    client = await make_client(make_settings(anthropic_api_key=None), model=None)
    body = (await client.post("/api/scenarios/run", json={"include_ai": True})).json()
    assert body["outcomes_differ"] is True
    for result in body["results"]:
        assert result["ai"]["status"] == "unavailable"
        assert result["ai"]["code"] == "agent_not_configured"
        assert result["assessment"]["status"] in ("caution", "favorable")


# Database


async def test_timestamps_are_utc_and_naive_datetimes_are_refused(session_factory):
    async with session_factory() as session:
        user = User(guest_token_hash="c" * 64)
        session.add(user)
        await session.commit()
        user_id = user.id
    async with session_factory() as session:
        stored = await session.get(User, user_id)
        assert stored.created_at.tzinfo is not None
        assert stored.created_at.utcoffset().total_seconds() == 0

    async with session_factory() as session:
        session.add(User(guest_token_hash="d" * 64, created_at=datetime(2027, 1, 1)))
        with pytest.raises(Exception, match="Naive datetime"):
            await session.commit()


async def test_deleting_a_farm_cascades_and_keeps_history(session_factory):
    async with session_factory() as session:
        user = User(guest_token_hash="e" * 64)
        session.add(user)
        await session.flush()
        farm = Farm(
            user_id=user.id,
            name="A",
            crops=[FarmCrop(crop="wheat", sowing_date=date(2026, 11, 10))],
        )
        session.add(farm)
        await session.flush()
        conversation = Conversation(user_id=user.id, farm_id=farm.id, title="t")
        session.add(conversation)
        await session.flush()
        session.add(Message(conversation_id=conversation.id, role="user", content="hi"))
        session.add(
            Recommendation(
                user_id=user.id,
                farm_id=farm.id,
                origin="assistant",
                intent="general",
                summary="s",
                risk_level="low",
                confidence="limited",
                advice={},
            )
        )
        await session.commit()
        farm_id = farm.id

    async with session_factory() as session:
        await session.delete(await session.get(Farm, farm_id))
        await session.commit()

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(FarmCrop)) == 0
        # A farmer's history outlives the farm it was about.
        assert (await session.scalar(select(Conversation))).farm_id is None
        assert (await session.scalar(select(Recommendation))).farm_id is None
        assert await session.scalar(select(func.count()).select_from(Message)) == 1


async def test_conversation_delete_cascades_to_messages(session_factory):
    async with session_factory() as session:
        user = User(guest_token_hash="f" * 64)
        session.add(user)
        await session.flush()
        conversation = Conversation(user_id=user.id, title="t")
        session.add(conversation)
        await session.flush()
        session.add(Message(conversation_id=conversation.id, role="user", content="hi"))
        await session.commit()
        conversation_id = conversation.id

    async with session_factory() as session:
        await session.delete(await session.get(Conversation, conversation_id))
        await session.commit()

    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Message)) == 0


async def test_weather_cache_records_source_and_timestamps(client, owm, session_factory):
    owm.get("/data/2.5/weather").respond(json=owm_current())
    await client.get("/api/weather/current", params={"lat": 30.9, "lon": 75.85})
    async with session_factory() as session:
        row = await session.scalar(select(WeatherCache))
    assert row.kind == "current"
    assert row.source == "OpenWeatherMap"
    assert row.latitude == 30.9
    assert row.observed_at is not None
    assert row.fetched_at.tzinfo == UTC
    assert row.expires_at > row.fetched_at
    assert "owm-test-secret" not in json.dumps(row.payload)
