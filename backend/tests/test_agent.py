"""The agent loop against a scripted model and real tools: the full cycle, limits and failures."""

import asyncio
import json
import uuid

import anthropic
import httpx
import httpx2
import pytest
from sqlalchemy import func, select

from app.agents.farm_agent import FarmAgent
from app.agents.output import FINAL_OUTPUT_SCHEMA
from app.agents.prompts import STATIC_SYSTEM_PROMPT, build_context_block
from app.core.errors import AgentError, AgentNotConfiguredError, AgentTimeoutError
from app.intelligence.types import Confidence, FarmingAdvice, Intent, RiskLevel
from app.models import Recommendation, User
from app.schemas.weather import DataProvenance
from app.services.openweather import OpenWeatherClient
from app.services.simulated_weather import SimulatedConditions, SimulatedWeatherProvider
from app.services.weather import WeatherService
from app.tools.base import ToolContext
from app.tools.registry import build_registry
from tests.factories import (
    FakeAnthropic,
    final_json,
    final_response,
    model_response,
    owm_current,
    owm_forecast,
    owm_geocode,
    text_block,
    tool_block,
)

LUDHIANA = {"latitude": 30.9, "longitude": 75.85}
ADVICE = dict(
    intent="irrigation_advice",
    recommendation="Consider postponing irrigation.",
    summary="Rain is forecast.",
    risk_level="moderate",
    confidence="limited",
)


@pytest.fixture
def weather_api(owm):
    owm.get("/data/2.5/weather").respond(json=owm_current(temp=24, humidity=80))
    owm.get("/data/2.5/forecast").respond(json=owm_forecast(pop=0.85, rain_3h=2.0, humidity=80))
    owm.get("/geo/1.0/direct").respond(json=owm_geocode())
    return owm


@pytest.fixture
async def tool_context(settings, session_factory):
    async with httpx.AsyncClient() as http:
        service = WeatherService(OpenWeatherClient(http, settings), session_factory, settings)
        yield ToolContext(weather=service, session_factory=session_factory)


def make_agent(settings, *script, repeat=None) -> tuple[FarmAgent, FakeAnthropic]:
    model = FakeAnthropic(script, repeat=repeat)
    return FarmAgent(model, settings, build_registry()), model


async def run(agent, context, message="Should I irrigate today?", **kwargs):
    return await agent.run(
        user_message=message,
        context_block=build_context_block({"preferred_language": "English"}, None),
        context=context,
        **kwargs,
    )


def tool_results(call: dict) -> list[dict]:
    return call["messages"][-1]["content"]


async def test_full_tool_cycle(settings, tool_context, weather_api):
    agent, model = make_agent(
        settings,
        model_response(
            "tool_use",
            text_block("Let me check the weather."),
            tool_block("get_current_weather", LUDHIANA),
        ),
        final_response(**ADVICE),
    )
    result = await run(agent, tool_context)

    # The backend ran the tool and sent the real result back, matched to Claude's request.
    assert len(model.calls) == 2
    block = tool_results(model.calls[1])[0]
    assert block["type"] == "tool_result"
    assert block["tool_use_id"] == "toolu_1"
    assert "is_error" not in block
    assert json.loads(block["content"])["temperature_c"] == 24

    # The assistant's request stays in the history, as the API requires.
    assert model.calls[1]["messages"][-2]["role"] == "assistant"

    assert result.iterations == 2
    assert result.tool_calls == 1
    assert result.tool_log[0]["name"] == "get_current_weather"
    assert result.tool_log[0]["ok"] is True
    assert result.tool_log[0]["provenance"] == "live"
    assert result.advice.generated_by == "claude_agent"


async def test_agent_can_request_more_tools_after_a_result(settings, tool_context, weather_api):
    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block("get_location_information", {"query": "Ludhiana"})),
        model_response(
            "tool_use",
            tool_block("get_current_weather", LUDHIANA, "toolu_2"),
            tool_block("get_weather_forecast", LUDHIANA, "toolu_3"),
        ),
        final_response(**ADVICE),
    )
    result = await run(agent, tool_context)
    assert [e["name"] for e in result.tool_log] == [
        "get_location_information",
        "get_current_weather",
        "get_weather_forecast",
    ]
    assert {b["tool_use_id"] for b in tool_results(model.calls[2])} == {"toolu_2", "toolu_3"}


async def test_weather_context_and_sources_come_from_tool_records_not_the_model(
    settings, tool_context, weather_api
):
    agent, _ = make_agent(
        settings,
        model_response(
            "tool_use", tool_block("assess_irrigation_need", {**LUDHIANA, "crop": "wheat"})
        ),
        final_response(**ADVICE),
    )
    advice = (await run(agent, tool_context)).advice
    context = advice.weather_context
    assert context.temperature_c == 24
    assert context.humidity_pct == 80
    assert context.rain_probability_pct == 85
    assert context.expected_rain_mm == 32  # 16 periods at 2 mm
    assert context.provenance == DataProvenance.LIVE
    assert advice.data_sources == ["OpenWeatherMap", "FarmAgent decision engine"]


def test_model_output_schema_has_no_slot_for_weather_or_sources():
    properties = FINAL_OUTPUT_SCHEMA["properties"]
    assert "weather_context" not in properties
    assert "data_sources" not in properties
    assert FINAL_OUTPUT_SCHEMA["additionalProperties"] is False
    assert set(FINAL_OUTPUT_SCHEMA["required"]) == set(properties)


async def test_assessment_tool_ignores_weather_supplied_by_the_model(
    settings, tool_context, weather_api
):
    agent, model = make_agent(
        settings,
        model_response(
            "tool_use",
            tool_block(
                "assess_irrigation_need", {**LUDHIANA, "crop": "wheat", "temperature_c": 50}
            ),
        ),
        final_response(intent="general", summary="ok"),
    )
    await run(agent, tool_context)
    block = tool_results(model.calls[1])[0]
    assert block["is_error"] is True
    assert json.loads(block["content"])["error"] == "invalid_arguments"


@pytest.mark.parametrize(
    ("name", "arguments", "bad_field"),
    [
        ("get_current_weather", {"latitude": 999, "longitude": 75.85}, "latitude"),
        ("get_current_weather", {"latitude": "north", "longitude": 75.85}, "latitude"),
        ("get_current_weather", {"latitude": 30.9}, "longitude"),
        ("get_weather_forecast", {**LUDHIANA, "horizon_hours": 9999}, "horizon_hours"),
        ("assess_irrigation_need", {**LUDHIANA}, "crop"),
        (
            "assess_irrigation_need",
            {**LUDHIANA, "crop": "wheat", "soil_moisture": "soggy"},
            "soil_moisture",
        ),
    ],
)
async def test_invalid_tool_arguments_go_back_to_the_model_as_errors(
    settings, tool_context, owm, name, arguments, bad_field
):
    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block(name, arguments)),
        final_response(intent="general", summary="I need a valid location."),
    )
    result = await run(agent, tool_context)
    block = tool_results(model.calls[1])[0]
    assert block["is_error"] is True
    content = json.loads(block["content"])
    assert content["error"] == "invalid_arguments"
    assert any(bad_field in p["field"] for p in content["problems"])
    assert not owm.calls
    assert result.tool_log[0]["ok"] is False


async def test_location_tool_requires_a_target(settings, tool_context):
    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block("get_location_information", {})),
        final_response(intent="general", summary="Which location?"),
    )
    await run(agent, tool_context)
    assert json.loads(tool_results(model.calls[1])[0]["content"])["error"] == "invalid_arguments"


async def test_unknown_tool_is_an_error_result(settings, tool_context):
    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block("launch_rocket", {})),
        final_response(intent="general", summary="Sorry."),
    )
    await run(agent, tool_context)
    assert json.loads(tool_results(model.calls[1])[0]["content"])["error"] == "unknown_tool"


async def test_location_not_found_is_an_error_result(settings, tool_context, owm):
    owm.get("/geo/1.0/direct").respond(json=[])
    agent, model = make_agent(
        settings,
        model_response(
            "tool_use", tool_block("get_location_information", {"query": "Nowhereville"})
        ),
        final_response(intent="general", summary="I could not find that place."),
    )
    await run(agent, tool_context)
    assert json.loads(tool_results(model.calls[1])[0]["content"])["error"] == "location_not_found"


async def test_excessive_tool_calls_are_stopped(make_settings, tool_context, weather_api):
    settings = make_settings(agent_max_tool_calls=3, agent_max_iterations=6)
    agent, model = make_agent(
        settings, repeat=model_response("tool_use", tool_block("get_current_weather", LUDHIANA))
    )
    result = await run(agent, tool_context)

    assert result.tool_calls == 3
    assert len(result.tool_log) == 3
    assert result.advice.generated_by == "safety_fallback"
    assert len(model.calls) == 6
    # Once the budget is spent, the model is told to stop calling tools.
    assert "tool_choice" not in model.calls[2]
    assert model.calls[3]["tool_choice"] == {"type": "none"}


async def test_one_turn_asking_for_too_many_tools_is_capped(
    make_settings, tool_context, weather_api
):
    settings = make_settings(agent_max_tool_calls=2)
    blocks = [tool_block("get_current_weather", LUDHIANA, f"toolu_{i}") for i in range(5)]
    agent, model = make_agent(
        settings,
        model_response("tool_use", *blocks),
        final_response(intent="general", summary="ok"),
    )
    result = await run(agent, tool_context)
    assert result.tool_calls == 2
    results = tool_results(model.calls[1])
    # Every tool_use still needs a tool_result, or the API rejects the next request.
    assert len(results) == 5
    assert [b.get("is_error", False) for b in results] == [False, False, True, True, True]
    assert json.loads(results[4]["content"])["error"] == "tool_call_limit"


async def test_iteration_limit_stops_the_loop(make_settings, tool_context, weather_api):
    settings = make_settings(agent_max_iterations=2, agent_max_tool_calls=40)
    agent, model = make_agent(
        settings, repeat=model_response("tool_use", tool_block("get_current_weather", LUDHIANA))
    )
    result = await run(agent, tool_context)
    assert len(model.calls) == 2
    assert result.advice.generated_by == "safety_fallback"


async def test_weather_advice_without_weather_is_sent_back_for_correction(
    settings, tool_context, weather_api
):
    agent, model = make_agent(
        settings,
        final_response(**ADVICE),
        model_response("tool_use", tool_block("get_current_weather", LUDHIANA)),
        final_response(**ADVICE),
    )
    result = await run(agent, tool_context)
    assert "without retrieving weather" in model.calls[1]["messages"][-1]["content"]
    assert result.advice.generated_by == "claude_agent"
    assert result.advice.recommendation == ADVICE["recommendation"]
    assert result.advice.weather_context is not None


async def test_model_that_will_not_fetch_weather_gets_its_advice_removed(settings, tool_context):
    agent, _ = make_agent(settings, repeat=final_response(**ADVICE))
    advice = (await run(agent, tool_context)).advice
    assert advice.generated_by == "safety_fallback"
    assert advice.recommendation is None
    assert advice.weather_context is None
    assert "Verified weather for this location" in advice.missing_information
    assert "could not verify the weather" in advice.summary


async def test_failed_weather_tools_remove_the_recommendation(settings, tool_context, owm):
    owm.get("/data/2.5/weather").respond(status_code=500)
    owm.get("/data/2.5/forecast").respond(status_code=500)
    agent, model = make_agent(
        settings,
        model_response(
            "tool_use", tool_block("assess_irrigation_need", {**LUDHIANA, "crop": "wheat"})
        ),
        final_response(**{**ADVICE, "summary": "Weather is unavailable, so check your soil."}),
    )
    result = await run(agent, tool_context)
    # The engine answered honestly rather than the tool failing.
    assessment = json.loads(tool_results(model.calls[1])[0]["content"])
    assert assessment["status"] == "insufficient_information"
    assert assessment["weather_provenance"] == "unavailable"
    advice = result.advice
    assert advice.recommendation is None
    assert advice.confidence == Confidence.LIMITED
    assert advice.risk_level == RiskLevel.UNCERTAIN
    assert "Verified weather for this location" in advice.missing_information
    assert advice.summary == "Weather is unavailable, so check your soil."


async def test_failed_weather_tool_is_reported_to_the_model(settings, tool_context, owm):
    owm.get("/data/2.5/weather").respond(status_code=401)
    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block("get_current_weather", LUDHIANA)),
        final_response(intent="general", summary="Weather is down."),
    )
    result = await run(agent, tool_context)
    block = tool_results(model.calls[1])[0]
    assert block["is_error"] is True
    assert json.loads(block["content"])["error"] == "weather_auth_failed"
    assert "owm-test-secret" not in block["content"]
    assert result.tool_log[0]["error_code"] == "weather_auth_failed"


async def test_stale_weather_caps_confidence(settings, tool_context, owm):
    from datetime import UTC, datetime, timedelta

    old = datetime.now(UTC) - timedelta(hours=5)
    owm.get("/data/2.5/weather").respond(json=owm_current(observed=old))
    agent, _ = make_agent(
        settings,
        model_response("tool_use", tool_block("get_current_weather", LUDHIANA)),
        final_response(**{**ADVICE, "intent": "weather_question", "confidence": "good"}),
    )
    advice = (await run(agent, tool_context)).advice
    assert advice.confidence == Confidence.LIMITED
    assert advice.weather_context.is_stale is True
    assert any("out of date" in item for item in advice.missing_information)


async def test_non_weather_questions_need_no_weather(settings, tool_context):
    agent, _ = make_agent(settings, final_response(intent="general", summary="Namaste."))
    result = await run(agent, tool_context, message="Hello")
    assert result.advice.generated_by == "claude_agent"
    assert result.advice.summary == "Namaste."
    assert result.tool_calls == 0


async def test_invalid_output_gets_one_correction(settings, tool_context):
    agent, model = make_agent(
        settings,
        model_response("end_turn", text_block("Sure, you should irrigate!")),
        final_response(intent="general", summary="Fixed."),
    )
    result = await run(agent, tool_context)
    assert result.advice.summary == "Fixed."
    assert "not valid against the required JSON schema" in model.calls[1]["messages"][-1]["content"]


async def test_output_with_a_bad_enum_is_rejected(settings, tool_context):
    agent, _ = make_agent(
        settings,
        model_response("end_turn", text_block(final_json(risk_level="catastrophic"))),
        final_response(intent="general", summary="Fixed."),
    )
    assert (await run(agent, tool_context)).advice.summary == "Fixed."


async def test_persistently_invalid_output_falls_back_safely(settings, tool_context):
    agent, model = make_agent(settings, repeat=model_response("end_turn", text_block("not json")))
    advice = (await run(agent, tool_context)).advice
    assert advice.generated_by == "safety_fallback"
    assert advice.recommendation is None
    assert len(model.calls) == 3


async def test_truncated_output_is_retried(settings, tool_context):
    agent, model = make_agent(
        settings,
        model_response("max_tokens", text_block('{"intent": "gen')),
        final_response(intent="general", summary="Shorter."),
    )
    assert (await run(agent, tool_context)).advice.summary == "Shorter."
    assert "cut off" in model.calls[1]["messages"][-1]["content"]


async def test_chemical_doses_are_sent_back_and_finally_removed(
    settings, tool_context, weather_api
):
    dosed = {
        **ADVICE,
        "intent": "pest_disease_risk",
        "recommendation": "Spray propiconazole at 200 ml/acre.",
    }
    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block("get_current_weather", LUDHIANA)),
        final_response(**dosed),
        final_response(**dosed),
        final_response(**dosed),
    )
    advice = (await run(agent, tool_context)).advice
    assert "chemical or product dose" in model.calls[2]["messages"][-1]["content"]
    assert advice.generated_by == "safety_fallback"
    assert advice.recommendation is None
    assert "200 ml" not in advice.summary


async def test_refusal_stop_reason_is_handled(settings, tool_context):
    agent, _ = make_agent(settings, model_response("refusal"))
    advice = (await run(agent, tool_context)).advice
    assert advice.generated_by == "safety_fallback"
    assert advice.recommendation is None


async def test_no_client_means_not_configured(settings, tool_context):
    agent = FarmAgent(None, settings, build_registry())
    with pytest.raises(AgentNotConfiguredError):
        await run(agent, tool_context)


async def test_total_timeout_is_enforced(make_settings, tool_context):
    class SlowModel(FakeAnthropic):
        async def create(self, **params):
            await asyncio.sleep(5)

    settings = make_settings(agent_total_timeout_seconds=0.05)
    agent = FarmAgent(SlowModel(), settings, build_registry())
    with pytest.raises(AgentTimeoutError):
        await run(agent, tool_context)


_MESSAGES_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _api_error(cls, status):
    response = httpx2.Response(status, request=_MESSAGES_REQUEST)
    return cls("anthropic-test-secret leaked in message", response=response, body=None)


@pytest.mark.parametrize(
    ("error", "exception", "code"),
    [
        (anthropic.APIConnectionError(request=_MESSAGES_REQUEST), AgentError, "agent_unavailable"),
        (anthropic.APITimeoutError(request=_MESSAGES_REQUEST), AgentTimeoutError, "agent_timeout"),
        (_api_error(anthropic.AuthenticationError, 401), AgentError, "agent_auth_failed"),
        (_api_error(anthropic.RateLimitError, 429), AgentError, "agent_rate_limited"),
        (_api_error(anthropic.InternalServerError, 500), AgentError, "agent_unavailable"),
    ],
)
async def test_claude_api_failures_become_safe_errors(
    settings, tool_context, error, exception, code
):
    agent, _ = make_agent(settings, error)
    with pytest.raises(exception) as caught:
        await run(agent, tool_context)
    assert caught.value.code == code
    assert "secret" not in caught.value.message


def _advice() -> dict:
    return {
        "intent": "irrigation_advice",
        "recommendation": "Wait.",
        "summary": "Rain is forecast.",
    }


async def test_save_is_refused_unless_the_farmer_asked(settings, session_factory, tool_context):
    async with session_factory() as session:
        user = User(guest_token_hash="a" * 64)
        session.add(user)
        await session.commit()
        user_id = user.id
    tool_context.user_id = user_id
    tool_context.allow_save = False

    agent, model = make_agent(
        settings,
        model_response("tool_use", tool_block("save_recommendation", _advice())),
        final_response(intent="general", summary="Do you want me to save that?"),
    )
    result = await run(agent, tool_context)
    assert json.loads(tool_results(model.calls[1])[0]["content"])["error"] == "refused"
    assert result.tool_log[0]["error_code"] == "refused"
    async with session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(Recommendation)) == 0


async def test_save_works_when_the_farmer_asked(settings, session_factory, tool_context):
    async with session_factory() as session:
        user = User(guest_token_hash="b" * 64)
        session.add(user)
        await session.commit()
        user_id = user.id
    tool_context.user_id = user_id
    tool_context.allow_save = True

    agent, _ = make_agent(
        settings,
        model_response("tool_use", tool_block("save_recommendation", _advice())),
        final_response(intent="general", summary="Saved."),
    )
    await run(agent, tool_context)
    assert len(tool_context.saved_recommendation_ids) == 1
    async with session_factory() as session:
        saved = await session.get(
            Recommendation, uuid.UUID(tool_context.saved_recommendation_ids[0])
        )
        assert saved.user_id == user_id
        assert saved.recommendation == "Wait."
        # The model cannot attach weather that was never retrieved.
        assert saved.weather_provenance is None
        assert saved.advice["weather_context"] is None


async def test_simulated_weather_is_labelled_all_the_way_through(settings):
    provider = SimulatedWeatherProvider(SimulatedConditions(24, 80, 85, 15, 2, "rain expected"))
    agent, _ = make_agent(
        settings,
        model_response(
            "tool_use", tool_block("assess_irrigation_need", {**LUDHIANA, "crop": "wheat"})
        ),
        final_response(**ADVICE),
    )
    advice = (await run(agent, ToolContext(weather=provider))).advice
    assert advice.weather_context.provenance == DataProvenance.SIMULATED
    assert advice.data_sources[0] == "Simulated (Scenario Lab)"


async def test_events_report_each_tool(settings, tool_context, weather_api):
    agent, _ = make_agent(
        settings,
        model_response("tool_use", tool_block("get_current_weather", LUDHIANA)),
        final_response(**ADVICE),
    )
    events = []

    async def emit(event):
        events.append(event)

    await run(agent, tool_context, emit=emit)
    assert [e["type"] for e in events] == ["status", "tool_start", "tool_end", "status"]
    assert events[2]["ok"] is True
    assert events[2]["provenance"] == "live"


async def test_history_is_sent_before_the_new_message(settings, tool_context):
    agent, model = make_agent(settings, final_response(intent="general", summary="Hi."))
    history = [
        {"role": "user", "content": "My field is in Ludhiana."},
        {"role": "assistant", "content": "Noted."},
    ]
    await run(agent, tool_context, message="And today?", history=history)
    assert model.calls[0]["messages"] == [*history, {"role": "user", "content": "And today?"}]


async def test_request_uses_configured_model_tools_and_structured_output(settings, tool_context):
    agent, model = make_agent(settings, final_response(intent="general", summary="Hi."))
    await run(agent, tool_context)
    call = model.calls[0]
    assert call["model"] == "claude-test-model"
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["system"][0]["text"] == STATIC_SYSTEM_PROMPT
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert {t["name"] for t in call["tools"]} == {
        "get_current_weather",
        "get_weather_forecast",
        "get_crop_information",
        "assess_irrigation_need",
        "assess_weather_pest_risk",
        "get_location_information",
        "save_recommendation",
    }
    for tool in call["tools"]:
        assert tool["description"]
        assert tool["input_schema"]["type"] == "object"


async def test_thinking_can_be_turned_off(make_settings, tool_context):
    agent, model = make_agent(
        make_settings(anthropic_adaptive_thinking=False),
        final_response(intent="general", summary="Hi."),
    )
    await run(agent, tool_context)
    assert "thinking" not in model.calls[0]


def test_system_prompt_states_the_non_negotiable_rules():
    prompt = STATIC_SYSTEM_PROMPT
    assert "Never invent" in prompt
    assert "Rain probability is the chance of rain" in prompt
    assert "It cannot show that one is present" in prompt
    assert "Never prescribe pesticides" in prompt


def test_context_block_marks_simulation_and_keeps_unknowns_null():
    block = build_context_block(
        {"preferred_language": "Punjabi"}, {"soil_type": None}, simulated=True
    )
    assert "SIMULATED" in block
    assert '"soil_type": null' in block
    assert "Punjabi" in block


# The real Anthropic SDK over a mock transport, so the SDK itself builds and parses each request.
# The SDK is built on httpx2, which respx does not intercept, hence its own MockTransport here.


def sdk_client(*responses) -> tuple[anthropic.AsyncAnthropic, list[httpx2.Request]]:
    requests: list[httpx2.Request] = []
    queue = list(responses)

    def handler(request: httpx2.Request) -> httpx2.Response:
        requests.append(request)
        status, body = queue.pop(0)
        return httpx2.Response(status, json=body)

    client = anthropic.AsyncAnthropic(
        api_key="anthropic-test-secret",
        max_retries=0,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)),
    )
    return client, requests


def _message(stop_reason: str, *content: dict) -> tuple[int, dict]:
    return 200, {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-test-model",
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
        "content": list(content),
    }


async def test_real_sdk_round_trip(settings, tool_context, owm):
    owm.get("/data/2.5/weather").respond(json=owm_current())
    client, requests = sdk_client(
        _message(
            "tool_use",
            {"type": "text", "text": "Checking."},
            {
                "type": "tool_use",
                "id": "toolu_real",
                "name": "get_current_weather",
                "input": LUDHIANA,
            },
        ),
        _message("end_turn", {"type": "text", "text": final_json(**ADVICE)}),
    )
    agent = FarmAgent(client, settings, build_registry())
    result = await run(agent, tool_context)
    assert result.advice.recommendation == ADVICE["recommendation"]

    first = json.loads(requests[0].content)
    assert first["model"] == "claude-test-model"
    assert first["thinking"] == {"type": "adaptive"}
    assert first["output_config"]["format"]["schema"]["additionalProperties"] is False
    assert len(first["tools"]) == 7
    assert all("input_schema" in tool for tool in first["tools"])
    sent = requests[0].headers
    assert "anthropic-test-secret" in (sent.get("x-api-key", "") + sent.get("authorization", ""))

    # The assistant's turn is replayed through the SDK, then the matching tool result.
    second = json.loads(requests[1].content)
    assert [b["type"] for b in second["messages"][-2]["content"]] == ["text", "tool_use"]
    assert second["messages"][-1]["content"][0]["tool_use_id"] == "toolu_real"


async def test_real_sdk_preserves_thinking_blocks_between_turns(settings, tool_context, owm):
    owm.get("/data/2.5/weather").respond(json=owm_current())
    thinking = {"type": "thinking", "thinking": "", "signature": "sig-abc"}
    client, requests = sdk_client(
        _message(
            "tool_use",
            thinking,
            {
                "type": "tool_use",
                "id": "toolu_real",
                "name": "get_current_weather",
                "input": LUDHIANA,
            },
        ),
        _message("end_turn", {"type": "text", "text": final_json(**ADVICE)}),
    )
    agent = FarmAgent(client, settings, build_registry())
    await run(agent, tool_context)
    replayed = json.loads(requests[1].content)["messages"][-2]["content"][0]
    assert replayed["type"] == "thinking"
    assert replayed["signature"] == "sig-abc"


@pytest.mark.parametrize(
    ("status", "error_type", "code"),
    [
        (500, "api_error", "agent_unavailable"),
        (401, "authentication_error", "agent_auth_failed"),
        (429, "rate_limit_error", "agent_rate_limited"),
        (400, "invalid_request_error", "agent_unavailable"),
    ],
)
async def test_real_sdk_http_errors_map_to_safe_errors(
    settings, tool_context, status, error_type, code
):
    client, _ = sdk_client(
        (status, {"type": "error", "error": {"type": error_type, "message": "internal detail"}})
    )
    agent = FarmAgent(client, settings, build_registry())
    with pytest.raises(AgentError) as caught:
        await run(agent, tool_context)
    assert caught.value.code == code
    assert "internal detail" not in caught.value.message


def test_advice_model_accepts_the_shape_the_spec_illustrates():
    advice = FarmingAdvice.model_validate(
        {
            "intent": "irrigation_advice",
            "recommendation": "Consider postponing irrigation",
            "summary": "Rain is forecast in the selected location.",
            "reasoning": ["Forecast indicates possible rainfall"],
            "weather_context": {
                "temperature_c": 25,
                "humidity_pct": 75,
                "rain_probability_pct": 80,
                "provenance": "live",
                "source": "OpenWeatherMap",
            },
            "risk_level": "moderate",
            "confidence": "limited",
            "missing_information": ["Current soil moisture"],
            "next_steps": ["Check soil moisture"],
            "data_sources": ["OpenWeatherMap"],
            "requires_expert_verification": False,
        }
    )
    assert advice.intent == Intent.IRRIGATION_ADVICE
