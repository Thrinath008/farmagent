"""Weather-related pest, disease and heat-stress risk. Conditions only, never a diagnosis.

Weather can show that conditions favour a problem. It cannot show that the problem is present, so
no output here claims an infestation exists, and nothing prescribes a chemical or a dose.
"""

from app.intelligence.confidence import assess_confidence
from app.intelligence.crops import CropProfile, ThreatRule, get_crop
from app.intelligence.sources import resolve
from app.intelligence.types import (
    Confidence,
    EnvironmentalCondition,
    ForecastConditions,
    PestRiskAssessment,
    PotentialRisk,
    RiskLevel,
    WeatherSnapshot,
)
from app.schemas.weather import DataProvenance

DISCLAIMER = (
    "This is a weather-based risk assessment, not a plant disease diagnosis. Weather cannot confirm "
    "that a pest or disease is present. Inspect the crop, and speak to your agricultural extension "
    "officer or Krishi Vigyan Kendra before any treatment."
)

# Design heuristics. See docs/agricultural-assumptions.md.
ELEVATED_PERIODS = 8  # at least 24 forecast hours in favourable conditions
MODERATE_PERIODS = 3  # at least 9 forecast hours
ELEVATED_DAYS = 2
PERIOD_HOURS = 3
PERIODS_PER_DAY = 8

_RANK = {RiskLevel.LOW: 0, RiskLevel.MODERATE: 1, RiskLevel.ELEVATED: 2}


def _period_matches(rule: ThreatRule, temp: float, humidity: float, rain_mm: float) -> bool:
    if rule.temp_min_c is not None and temp < rule.temp_min_c:
        return False
    if rule.temp_max_c is not None and temp > rule.temp_max_c:
        return False
    if rule.needs_rain and rain_mm <= 0:
        return False
    if rule.humidity_min_pct is None:
        return True
    return humidity >= rule.humidity_min_pct or (rule.rain_counts_as_moisture and rain_mm > 0)


def _evaluate_daily(rule: ThreatRule, periods: list[ForecastConditions]) -> tuple[RiskLevel, str]:
    days = [periods[i : i + PERIODS_PER_DAY] for i in range(0, len(periods), PERIODS_PER_DAY)]
    days = [day for day in days if len(day) == PERIODS_PER_DAY]
    if not days:
        return (
            RiskLevel.UNCERTAIN,
            "The forecast is too short to compare daily minimums and maximums.",
        )
    low, high = rule.daily_min_range_c, rule.daily_max_range_c
    matching = sum(
        1
        for day in days
        if low[0] <= min(p.temperature_c for p in day) <= low[1]
        and high[0] <= max(p.temperature_c for p in day) <= high[1]
        and max(p.humidity_pct for p in day) >= rule.humidity_min_pct
    )
    evidence = f"{matching} of the next {len(days)} forecast days fit these conditions."
    if matching >= ELEVATED_DAYS:
        return RiskLevel.ELEVATED, evidence
    return (RiskLevel.MODERATE if matching == 1 else RiskLevel.LOW), evidence


def _evaluate_periods(rule: ThreatRule, periods: list[ForecastConditions]) -> tuple[RiskLevel, str]:
    matching = sum(
        1 for p in periods if _period_matches(rule, p.temperature_c, p.humidity_pct, p.rain_mm)
    )
    evidence = (
        f"{matching * PERIOD_HOURS} of the next {len(periods) * PERIOD_HOURS} forecast hours fit "
        "these conditions."
    )
    if matching >= ELEVATED_PERIODS:
        return RiskLevel.ELEVATED, evidence
    return (RiskLevel.MODERATE if matching >= MODERATE_PERIODS else RiskLevel.LOW), evidence


def _evaluate_rule(
    rule: ThreatRule, snapshot: WeatherSnapshot, stage_id: str | None
) -> PotentialRisk:
    evidence: list[str] = []

    if not rule.weather_evaluable:
        classification = RiskLevel.UNCERTAIN
        evidence.append("No verified weather trigger exists, so this needs scouting in the field.")
    elif stage_id is not None and stage_id not in rule.susceptible_stages:
        classification = RiskLevel.LOW
        evidence.append("The crop is not at a stage this affects.")
    elif snapshot.periods:
        evaluate = _evaluate_daily if rule.daily_min_range_c else _evaluate_periods
        classification, line = evaluate(rule, snapshot.periods)
        evidence.append(line)
    elif snapshot.temperature_c is None or (
        rule.humidity_min_pct is not None and snapshot.humidity_pct is None
    ):
        classification = RiskLevel.UNCERTAIN
        evidence.append("Temperature or humidity is missing, so this could not be judged.")
    elif rule.daily_min_range_c:
        classification = RiskLevel.UNCERTAIN
        evidence.append(
            "This needs a forecast of daily minimums and maximums, which is unavailable."
        )
    else:
        fits = _period_matches(
            rule, snapshot.temperature_c, snapshot.humidity_pct or 0, snapshot.rain_last_1h_mm or 0
        )
        # One reading cannot show a sustained spell, so it can never reach "elevated".
        classification = RiskLevel.MODERATE if fits else RiskLevel.UNCERTAIN
        evidence.append(
            "Current conditions fit. No forecast is available to show how long that lasts."
            if fits
            else "Current conditions do not fit, but no forecast is available to look ahead."
        )

    if stage_id is None and rule.weather_evaluable:
        evidence.append("Growth stage was not provided, so it was not checked against this risk.")

    return PotentialRisk(
        id=rule.id,
        name=rule.name,
        category=rule.category,
        classification=classification,
        favorable_conditions=rule.favorable_conditions,
        evidence=evidence,
        monitoring_actions=list(rule.monitoring_actions),
        regional_note=rule.regional_note,
        sources=resolve(rule.source_ids),
    )


def _overall(risks: list[PotentialRisk], rules: dict[str, ThreatRule]) -> RiskLevel:
    judged = [r.classification for r in risks if rules[r.id].weather_evaluable]
    known = [c for c in judged if c in _RANK]
    highest = max(known, key=_RANK.__getitem__, default=None)
    if highest in (RiskLevel.MODERATE, RiskLevel.ELEVATED):
        return highest
    # Not all clear if any evaluation lacked the data to decide.
    return RiskLevel.UNCERTAIN if len(known) != len(judged) or not judged else RiskLevel.LOW


def _conditions(snapshot: WeatherSnapshot) -> list[EnvironmentalCondition]:
    rows: list[EnvironmentalCondition] = []

    def add(label: str, value: float | None, unit: str) -> None:
        if value is not None:
            rows.append(EnvironmentalCondition(label=label, value=f"{value:g}{unit}"))

    add("Temperature now", snapshot.temperature_c, " °C")
    add("Humidity now", snapshot.humidity_pct, "%")
    add("Coolest in next 48 h", snapshot.temp_min_48h_c, " °C")
    add("Warmest in next 48 h", snapshot.temp_max_48h_c, " °C")
    add("Average humidity, next 48 h", snapshot.humidity_mean_48h_pct, "%")
    add("Forecast rain, next 48 h", snapshot.rain_next_48h_mm, " mm")
    add("Highest rain chance, next 48 h", snapshot.rain_prob_max_48h_pct, "%")
    return rows


def _unassessed(
    crop_id: str,
    profile: CropProfile | None,
    stage_id: str | None,
    explanation: str,
    missing: list[str],
) -> PestRiskAssessment:
    stage = profile.stage(stage_id) if profile else None
    return PestRiskAssessment(
        crop=crop_id,
        crop_name=profile.name if profile else crop_id,
        growth_stage=stage.id if stage else stage_id,
        growth_stage_label=stage.label if stage else None,
        overall_classification=RiskLevel.UNCERTAIN,
        headline="Risk could not be assessed",
        explanation=explanation,
        risks=[],
        environmental_conditions=[],
        crop_sensitivity=profile.support_note if profile else "",
        missing_information=missing,
        confidence=Confidence.INSUFFICIENT,
        confidence_note="An assessment could not be made from the available information.",
        disclaimer=DISCLAIMER,
        weather_provenance=DataProvenance.UNAVAILABLE,
    )


def assess_pest_risk(
    crop: str, growth_stage: str | None, snapshot: WeatherSnapshot | None
) -> PestRiskAssessment:
    profile = get_crop(crop)
    if profile is None or profile.support != "rules_implemented":
        note = profile.support_note if profile else f"{crop} is not a crop FarmAgent recognises."
        result = _unassessed(crop, profile, growth_stage, note, ["Crop-specific risk rules"])
        if snapshot is not None:
            result.weather_provenance = snapshot.provenance
            result.environmental_conditions = _conditions(snapshot)
        return result

    if snapshot is None or snapshot.provenance == DataProvenance.UNAVAILABLE:
        return _unassessed(
            profile.id,
            profile,
            growth_stage,
            "Verified weather could not be retrieved, so risk was not assessed.",
            ["Verified weather for this location"],
        )

    stage = profile.stage(growth_stage)
    stage_id = stage.id if stage else None
    rules = {rule.id: rule for rule in profile.threats}
    risks = [_evaluate_rule(rule, snapshot, stage_id) for rule in profile.threats]
    order = {RiskLevel.ELEVATED: 0, RiskLevel.MODERATE: 1, RiskLevel.UNCERTAIN: 2, RiskLevel.LOW: 3}
    risks.sort(key=lambda r: order[r.classification])
    overall = _overall(risks, rules)

    critical_missing: list[str] = []
    if stage is None:
        critical_missing.append("Crop growth stage")
    if not snapshot.forecast_available:
        critical_missing.append("Weather forecast")
    if snapshot.humidity_pct is None and snapshot.humidity_mean_48h_pct is None:
        critical_missing.append("Humidity")
    # Measured leaf wetness is never available here, so the result can reach "moderate" at most.
    secondary_missing = ["Leaf wetness measurement", "Observations from your own field"]
    confidence, note = assess_confidence(
        snapshot, critical_missing=critical_missing, secondary_missing=secondary_missing
    )

    elevated = [r.name for r in risks if r.classification == RiskLevel.ELEVATED]
    moderate = [r.name for r in risks if r.classification == RiskLevel.MODERATE]
    headline, explanation = _describe(overall, elevated, moderate)
    critical_stage = stage.label if stage else "an unknown stage"
    return PestRiskAssessment(
        crop=profile.id,
        crop_name=profile.name,
        growth_stage=stage_id,
        growth_stage_label=stage.label if stage else None,
        overall_classification=overall,
        headline=headline,
        explanation=explanation,
        risks=risks,
        environmental_conditions=_conditions(snapshot),
        crop_sensitivity=(
            f"{profile.name} at {critical_stage}. " + " ".join(profile.weather_sensitivities[:2])
        ),
        missing_information=critical_missing + secondary_missing,
        confidence=confidence,
        confidence_note=note,
        disclaimer=DISCLAIMER,
        weather_provenance=snapshot.provenance,
    )


def _describe(overall: RiskLevel, elevated: list[str], moderate: list[str]) -> tuple[str, str]:
    if overall == RiskLevel.ELEVATED:
        return (
            f"Conditions favour {_join(elevated)}",
            "The forecast fits the conditions published for this problem for a sustained period. "
            "That raises the need to scout. It does not mean the problem is in your field.",
        )
    if overall == RiskLevel.MODERATE:
        return (
            f"Some favourable conditions for {_join(moderate)}",
            "The forecast partly fits the conditions published for this problem. Keep scouting as "
            "normal. This does not mean the problem is in your field.",
        )
    if overall == RiskLevel.UNCERTAIN:
        return (
            "Risk is uncertain",
            "There was not enough data to judge every risk, so this should not be read as all clear.",
        )
    return (
        "Few favourable conditions in the forecast",
        "The forecast does not fit the conditions published for these problems. Keep scouting, "
        "because weather is only part of the picture.",
    )


def _join(names: list[str]) -> str:
    lowered = [n[0].lower() + n[1:] for n in names]
    if len(lowered) <= 1:
        return "".join(lowered)
    return ", ".join(lowered[:-1]) + " and " + lowered[-1]
