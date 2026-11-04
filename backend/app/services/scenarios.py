"""The Scenario Lab: two fixed, simulated weather scenarios run through the real pipeline.

Simulated weather enters through the same provider interface as live weather, so these results come
from the production engine and, if requested, the production agent loop. Nothing here is a canned
answer.
"""

import asyncio
from datetime import date

from app.agents.farm_agent import FarmAgent
from app.agents.prompts import build_context_block
from app.core.errors import AppError
from app.intelligence.irrigation import IrrigationInput, assess_irrigation
from app.intelligence.pest_risk import assess_pest_risk
from app.intelligence.recommendation import advice_from_irrigation
from app.intelligence.types import SoilMoisture
from app.schemas.api import (
    FactorComparison,
    InputDifference,
    ScenarioAiResult,
    ScenarioDefinition,
    ScenarioInputs,
    ScenarioResult,
    ScenarioRunResponse,
)
from app.services.assessments import load_weather
from app.services.simulated_weather import (
    REFERENCE_TIME,
    SCENARIO_COORDINATES,
    SimulatedConditions,
    SimulatedWeatherProvider,
)
from app.tools.base import ToolContext

_WIND_MS = 2.0
_REFERENCE_DATE: date = REFERENCE_TIME.date()

SCENARIOS: dict[str, ScenarioDefinition] = {
    "A": ScenarioDefinition(
        id="A",
        title="Rain expected",
        description="Mild and humid, with meaningful rain likely in the next two days.",
        inputs=ScenarioInputs(
            temperature_c=24,
            humidity_pct=80,
            rain_probability_pct=85,
            expected_rain_mm=15,
            wind_speed_ms=_WIND_MS,
            crop="wheat",
            growth_stage="vegetative",
            soil_moisture=SoilMoisture.UNKNOWN,
        ),
    ),
    "B": ScenarioDefinition(
        id="B",
        title="Hot and dry",
        description="Hot, dry air with no rain expected and low soil moisture.",
        inputs=ScenarioInputs(
            temperature_c=36,
            humidity_pct=30,
            rain_probability_pct=5,
            expected_rain_mm=0,
            wind_speed_ms=_WIND_MS,
            crop="wheat",
            growth_stage="vegetative",
            soil_moisture=SoilMoisture.LOW,
        ),
    ),
}

_NOTICE = (
    "All weather on this page is simulated to demonstrate how the decision engine responds. It is "
    "not real weather and must not be used to make decisions in the field."
)
_DESCRIPTIONS = {"A": "simulated rain expected", "B": "simulated hot and dry weather"}


def _provider(definition: ScenarioDefinition) -> SimulatedWeatherProvider:
    i = definition.inputs
    return SimulatedWeatherProvider(
        SimulatedConditions(
            temperature_c=i.temperature_c,
            humidity_pct=i.humidity_pct,
            rain_probability_pct=i.rain_probability_pct,
            expected_rain_mm=i.expected_rain_mm,
            wind_speed_ms=i.wind_speed_ms,
            description=_DESCRIPTIONS[definition.id],
        )
    )


async def _run_engine(definition: ScenarioDefinition):
    i = definition.inputs
    bundle = await load_weather(_provider(definition), *SCENARIO_COORDINATES)
    snapshot = bundle.snapshot
    assessment = assess_irrigation(
        IrrigationInput(
            crop=i.crop,
            growth_stage=i.growth_stage,
            soil_moisture=i.soil_moisture,
            on_date=_REFERENCE_DATE,
        ),
        snapshot,
    )
    pest_risk = assess_pest_risk(i.crop, i.growth_stage, snapshot)
    return assessment, pest_risk, advice_from_irrigation(assessment, snapshot)


async def _run_agent(agent: FarmAgent, definition: ScenarioDefinition) -> ScenarioAiResult:
    i = definition.inputs
    latitude, longitude = SCENARIO_COORDINATES
    moisture = (
        "I have not checked the soil moisture."
        if i.soil_moisture == SoilMoisture.UNKNOWN
        else f"The soil moisture is {i.soil_moisture.value}."
    )
    question = f"Should I irrigate my wheat field? It is at the vegetative stage. {moisture}"
    farm = {
        "name": "Scenario Lab field",
        "latitude": latitude,
        "longitude": longitude,
        "crops": [
            {"crop": i.crop, "growth_stage": i.growth_stage, "rule_support": "rules_implemented"}
        ],
    }
    context_block = build_context_block(
        {"display_name": None, "preferred_language": "English"},
        farm,
        simulated=True,
        now=REFERENCE_TIME,
    )
    context = ToolContext(weather=_provider(definition), allow_save=False, origin="scenario_lab")
    try:
        result = await agent.run(
            user_message=question, context_block=context_block, context=context
        )
    except AppError as exc:
        return ScenarioAiResult(status="unavailable", message=exc.message, code=exc.code)
    return ScenarioAiResult(status="completed", advice=result.advice, tool_log=result.tool_log)


async def run_scenarios(
    scenario_ids: list[str], agent: FarmAgent, *, include_ai: bool
) -> ScenarioRunResponse:
    definitions = [SCENARIOS[sid] for sid in dict.fromkeys(scenario_ids)]
    engine_results = [await _run_engine(d) for d in definitions]

    if include_ai:
        ai_results = await asyncio.gather(*(_run_agent(agent, d) for d in definitions))
    else:
        ai_results = [ScenarioAiResult(status="not_requested") for _ in definitions]

    results = [
        ScenarioResult(
            definition=definition, assessment=assessment, pest_risk=pest_risk, advice=advice, ai=ai
        )
        for definition, (assessment, pest_risk, advice), ai in zip(
            definitions, engine_results, ai_results, strict=True
        )
    ]
    return ScenarioRunResponse(
        notice=_NOTICE,
        results=results,
        input_differences=_input_differences(definitions),
        factor_comparison=_factor_comparison(results),
        outcomes_differ=len({(r.assessment.status, r.assessment.action) for r in results}) > 1,
    )


def _input_differences(definitions: list[ScenarioDefinition]) -> list[InputDifference]:
    rows = [
        ("temperature_c", "Temperature", lambda i: f"{i.temperature_c:g} °C"),
        ("humidity_pct", "Humidity", lambda i: f"{i.humidity_pct:g}%"),
        ("rain_probability_pct", "Rain probability", lambda i: f"{i.rain_probability_pct:g}%"),
        ("expected_rain_mm", "Expected rainfall", lambda i: f"{i.expected_rain_mm:g} mm"),
        ("soil_moisture", "Soil moisture", lambda i: _moisture_label(i.soil_moisture)),
        ("crop", "Crop", lambda i: i.crop.capitalize()),
        ("growth_stage", "Growth stage", lambda i: i.growth_stage.capitalize()),
    ]
    differences = []
    for key, label, read in rows:
        values = {d.id: read(d.inputs) for d in definitions}
        differences.append(
            InputDifference(
                key=key, label=label, values=values, differs=len(set(values.values())) > 1
            )
        )
    return differences


def _moisture_label(moisture: SoilMoisture) -> str:
    return "Not provided" if moisture == SoilMoisture.UNKNOWN else moisture.value.capitalize()


def _factor_comparison(results: list[ScenarioResult]) -> list[FactorComparison]:
    comparison: dict[str, FactorComparison] = {}
    for result in results:
        sid = result.definition.id
        for factor in result.assessment.factors:
            row = comparison.setdefault(
                factor.key,
                FactorComparison(
                    key=factor.key, label=factor.label, values={}, weights={}, explanations={}
                ),
            )
            row.values[sid] = factor.value
            row.weights[sid] = factor.weight
            row.explanations[sid] = factor.explanation
    return list(comparison.values())
