"""Turn engine assessments into the shared FarmingAdvice shape, with no AI involved."""

from app.intelligence.types import (
    FarmingAdvice,
    Intent,
    IrrigationAssessment,
    IrrigationStatus,
    PestRiskAssessment,
    RiskLevel,
    WeatherContext,
    WeatherSnapshot,
)

ENGINE_SOURCE = "FarmAgent decision engine"


def weather_context_from_snapshot(snapshot: WeatherSnapshot) -> WeatherContext:
    return WeatherContext(
        temperature_c=snapshot.temperature_c,
        humidity_pct=snapshot.humidity_pct,
        rain_probability_pct=snapshot.rain_prob_max_48h_pct,
        expected_rain_mm=snapshot.rain_next_48h_mm,
        wind_speed_ms=snapshot.wind_speed_ms,
        description=snapshot.description,
        location_name=snapshot.location_name,
        provenance=snapshot.provenance,
        source=snapshot.source,
        observed_at=snapshot.observed_at,
        is_stale=snapshot.is_stale,
    )


def _sources(snapshot: WeatherSnapshot | None) -> list[str]:
    return ([snapshot.source] if snapshot else []) + [ENGINE_SOURCE]


def advice_from_irrigation(
    assessment: IrrigationAssessment, snapshot: WeatherSnapshot | None
) -> FarmingAdvice:
    has_advice = assessment.status != IrrigationStatus.INSUFFICIENT
    return FarmingAdvice(
        intent=Intent.IRRIGATION_ADVICE,
        recommendation=assessment.headline if has_advice else None,
        summary=assessment.summary,
        reasoning=assessment.supporting_factors,
        weather_context=weather_context_from_snapshot(snapshot) if snapshot else None,
        risk_level=assessment.risk_level,
        confidence=assessment.confidence,
        missing_information=assessment.missing_information,
        next_steps=[assessment.next_action, *assessment.next_steps],
        data_sources=_sources(snapshot),
        requires_expert_verification=False,
        generated_by="decision_engine",
    )


def advice_from_pest_risk(
    assessment: PestRiskAssessment, snapshot: WeatherSnapshot | None
) -> FarmingAdvice:
    flagged = [
        r for r in assessment.risks if r.classification in (RiskLevel.ELEVATED, RiskLevel.MODERATE)
    ]
    steps = [action for risk in flagged for action in risk.monitoring_actions]
    return FarmingAdvice(
        intent=Intent.PEST_DISEASE_RISK,
        recommendation=assessment.headline if assessment.risks else None,
        summary=f"{assessment.explanation} {assessment.disclaimer}",
        reasoning=[
            line for risk in flagged for line in (f"{risk.name}: {e}" for e in risk.evidence)
        ],
        weather_context=weather_context_from_snapshot(snapshot) if snapshot else None,
        risk_level=assessment.overall_classification,
        confidence=assessment.confidence,
        missing_information=assessment.missing_information,
        next_steps=steps,
        data_sources=_sources(snapshot),
        requires_expert_verification=assessment.overall_classification == RiskLevel.ELEVATED,
        generated_by="decision_engine",
    )
