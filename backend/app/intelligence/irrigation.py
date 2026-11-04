"""Irrigation assessment: explainable, deterministic scoring with hard safety gates.

The same inputs always give the same output. Each factor records its signed weight and its reason.
Weights and thresholds marked as design heuristics in docs/agricultural-assumptions.md are FarmAgent
choices, not published agronomy. Status labels are rule-based and not scientifically calibrated.
"""

from dataclasses import dataclass
from datetime import date

from app.intelligence.confidence import assess_confidence
from app.intelligence.crops import CropProfile, get_crop
from app.intelligence.growth_stages import rain_interval_extension_days, schedule_for_crop
from app.intelligence.sources import resolve
from app.intelligence.types import (
    Confidence,
    DecisionFactor,
    FactorDirection,
    IrrigationAction,
    IrrigationAssessment,
    IrrigationMethod,
    IrrigationStatus,
    RiskLevel,
    SoilMoisture,
    SoilType,
    WeatherSnapshot,
)
from app.schemas.weather import DataProvenance

# Design heuristics. See docs/agricultural-assumptions.md.
RAIN_STRONG_MM = 10.0  # PAU's rain rule is stated per 1 cm
RAIN_STRONG_PROB = 60.0
RAIN_PARTIAL_MM = 5.0
RAIN_PARTIAL_PROB = 50.0
RAIN_NEGLIGIBLE_MM = 1.0
RAIN_NEGLIGIBLE_PROB = 30.0
RAIN_SMALL_MM = 2.0
RECENT_RAIN_STRONG_MM = 10.0
RECENT_RAIN_PARTIAL_MM = 5.0
HIGH_DEMAND_TEMP_C = 35.0
HIGH_DEMAND_RH = 40.0
RAISED_DEMAND_RH = 60.0
LOW_DEMAND_TEMP_C = 25.0
LOW_DEMAND_RH = 70.0
WINDY_MS = 8.0
FAVORABLE_MIN_SCORE = 3

# FAO-56 Table 19: theta_FC minus theta_WP, as mm of available water per metre of soil.
# Table 19 has no clay loam row, so clay loam uses the nearest row, silt clay loam.
SOIL_WATER_MM_PER_M: dict[SoilType, tuple[int, int]] = {
    SoilType.SANDY: (50, 110),
    SoilType.LOAMY_SAND: (60, 120),
    SoilType.SANDY_LOAM: (110, 150),
    SoilType.LOAM: (130, 180),
    SoilType.SILT_LOAM: (130, 190),
    SoilType.CLAY_LOAM: (130, 180),
    SoilType.CLAY: (120, 200),
}
_LIGHT_SOILS = {SoilType.SANDY, SoilType.LOAMY_SAND}
_HEAVY_SOILS = {SoilType.CLAY, SoilType.CLAY_LOAM}

_LIMITATION_RULES = (
    "These are rule-based labels from published guidance and FarmAgent's own design choices. They "
    "are not scientifically calibrated and have not been validated in field trials."
)
_DECISION_DEPENDS = (
    "The actual decision also depends on your soil moisture, what the crop needs at this stage, and "
    "how much rain actually falls."
)


@dataclass(frozen=True)
class IrrigationInput:
    crop: str
    growth_stage: str | None = None
    soil_type: SoilType = SoilType.UNKNOWN
    soil_moisture: SoilMoisture = SoilMoisture.UNKNOWN
    irrigation_method: IrrigationMethod = IrrigationMethod.UNKNOWN
    recent_rainfall_mm: float | None = None
    sowing_date: date | None = None
    on_date: date | None = None


def _factor(
    key: str,
    label: str,
    value: str,
    weight: int,
    explanation: str,
    *source_ids: str,
    unknown: bool = False,
) -> DecisionFactor:
    if unknown:
        direction = FactorDirection.UNKNOWN
    elif weight > 0:
        direction = FactorDirection.SUPPORTS_IRRIGATING
    elif weight < 0:
        direction = FactorDirection.AGAINST_IRRIGATING
    else:
        direction = FactorDirection.NEUTRAL
    return DecisionFactor(
        key=key,
        label=label,
        value=value,
        direction=direction,
        weight=weight,
        explanation=explanation,
        source_ids=list(source_ids),
    )


def _soil_moisture_factor(moisture: SoilMoisture) -> DecisionFactor:
    match moisture:
        case SoilMoisture.LOW:
            return _factor(
                "soil_moisture",
                "Soil moisture",
                "Low",
                3,
                "You reported low soil moisture, the most direct sign the crop may need water.",
            )
        case SoilMoisture.ADEQUATE:
            return _factor(
                "soil_moisture",
                "Soil moisture",
                "Adequate",
                -1,
                "You reported adequate soil moisture, so there is no urgent need for water.",
            )
        case SoilMoisture.HIGH:
            return _factor(
                "soil_moisture",
                "Soil moisture",
                "High or waterlogged",
                -4,
                "You reported wet soil. PAU advises avoiding excessive irrigation.",
                "pau_pop_rabi_2025",
            )
    return _factor(
        "soil_moisture",
        "Soil moisture",
        "Not provided",
        0,
        "Soil moisture was not provided. It is the most direct indicator of water need.",
        unknown=True,
    )


def _forecast_rain_factor(snapshot: WeatherSnapshot, on_date: date) -> DecisionFactor:
    mm = snapshot.rain_next_48h_mm
    prob = snapshot.rain_prob_max_48h_pct
    if mm is None or prob is None:
        shown = f"up to {prob:.0f}% chance, amount unknown" if prob is not None else "Not available"
        return _factor(
            "forecast_rain",
            "Forecast rain (48 h)",
            shown,
            0,
            "No rainfall amount is available. Probability alone does not say how much would fall.",
            unknown=True,
        )

    value = f"{mm:.1f} mm, up to {prob:.0f}% chance"
    extension = rain_interval_extension_days(mm, on_date)
    if mm >= RAIN_STRONG_MM and prob >= RAIN_STRONG_PROB:
        return _factor(
            "forecast_rain",
            "Forecast rain (48 h)",
            value,
            -3,
            f"Meaningful rain is likely. If it falls, PAU's rule would lengthen the interval to the "
            f"next irrigation by about {extension:g} days.",
            "pau_pop_rabi_2025",
        )
    if mm >= RAIN_PARTIAL_MM and prob >= RAIN_PARTIAL_PROB:
        return _factor(
            "forecast_rain",
            "Forecast rain (48 h)",
            value,
            -2,
            f"Some rain is reasonably likely. If it falls, PAU's rule would lengthen the interval to "
            f"the next irrigation by about {extension:g} days.",
            "pau_pop_rabi_2025",
        )
    if mm < RAIN_SMALL_MM and prob >= RAIN_STRONG_PROB:
        return _factor(
            "forecast_rain",
            "Forecast rain (48 h)",
            value,
            0,
            "Rain is likely, but the forecast amount is small, so it should not replace irrigation.",
        )
    if mm < RAIN_NEGLIGIBLE_MM and prob <= RAIN_NEGLIGIBLE_PROB:
        return _factor(
            "forecast_rain",
            "Forecast rain (48 h)",
            value,
            1,
            "No meaningful rain is forecast in the next two days.",
        )
    return _factor(
        "forecast_rain",
        "Forecast rain (48 h)",
        value,
        0,
        "The rain forecast is too uncertain or too small to change the decision on its own.",
    )


def _recent_rain_factor(recent_mm: float | None, on_date: date) -> DecisionFactor:
    if recent_mm is None:
        return _factor(
            "recent_rain",
            "Recent rain",
            "Not provided",
            0,
            "The weather provider gives no multi-day rainfall history, so enter it if you know it.",
            unknown=True,
        )
    value = f"{recent_mm:.1f} mm"
    extension = rain_interval_extension_days(recent_mm, on_date)
    if recent_mm >= RECENT_RAIN_STRONG_MM:
        return _factor(
            "recent_rain",
            "Recent rain",
            value,
            -2,
            f"PAU's rule lengthens the interval to the next irrigation by about {extension:g} days "
            "for this much rain.",
            "pau_pop_rabi_2025",
        )
    if recent_mm >= RECENT_RAIN_PARTIAL_MM:
        return _factor(
            "recent_rain",
            "Recent rain",
            value,
            -1,
            f"PAU's rule lengthens the interval to the next irrigation by about {extension:g} days "
            "for this much rain.",
            "pau_pop_rabi_2025",
        )
    return _factor(
        "recent_rain", "Recent rain", value, 0, "Too little recent rain to change the decision."
    )


def _demand_factor(
    snapshot: WeatherSnapshot, profile: CropProfile, stage_id: str | None
) -> DecisionFactor:
    temps = [t for t in (snapshot.temperature_c, snapshot.temp_max_48h_c) if t is not None]
    humidity = snapshot.humidity_mean_48h_pct
    if humidity is None:
        humidity = snapshot.humidity_pct
    if not temps or humidity is None:
        return _factor(
            "water_demand",
            "Heat and dryness",
            "Not available",
            0,
            "Temperature or humidity is missing, so crop water demand could not be judged.",
            unknown=True,
        )

    temp = max(temps)
    value = f"up to {temp:.0f} °C, {humidity:.0f}% humidity"
    stage = profile.stage(stage_id)
    upper = stage.temp_max_range_c[1] if stage and stage.temp_max_range_c else None

    if temp >= HIGH_DEMAND_TEMP_C and humidity <= HIGH_DEMAND_RH:
        return _factor(
            "water_demand",
            "Heat and dryness",
            value,
            2,
            "Hot, dry air raises crop water use and the risk of water stress.",
            "singh_2023_terminal_heat",
        )
    if upper is not None and temp > upper and humidity <= RAISED_DEMAND_RH:
        return _factor(
            "water_demand",
            "Heat and dryness",
            value,
            1,
            f"Warmer than PAU's {upper:.0f} °C upper range for this stage, with fairly dry air.",
            "pau_pop_rabi_2025",
        )
    if temp <= LOW_DEMAND_TEMP_C and humidity >= LOW_DEMAND_RH:
        return _factor(
            "water_demand",
            "Heat and dryness",
            value,
            -1,
            "Mild, humid conditions keep crop water use down.",
        )
    return _factor(
        "water_demand",
        "Heat and dryness",
        value,
        0,
        "Temperature and humidity point to ordinary crop water use.",
    )


def _stage_factor(profile: CropProfile, stage_id: str | None) -> DecisionFactor:
    stage = profile.stage(stage_id)
    if stage is None:
        return _factor(
            "growth_stage",
            "Growth stage",
            "Not provided",
            0,
            "Water needs change through the season, so the stage matters for this decision.",
            unknown=True,
        )
    if stage.id in profile.no_irrigation_stages:
        return _factor(
            "growth_stage",
            "Growth stage",
            stage.label,
            -3,
            "The crop is at the end of its season, when irrigation no longer helps grain development.",
            "pau_pop_rabi_2025",
        )
    if stage.irrigation_critical:
        return _factor(
            "growth_stage",
            "Growth stage",
            stage.label,
            1,
            "This is one of the stages where water stress matters most.",
            "tnau_irrigation",
        )
    return _factor(
        "growth_stage",
        "Growth stage",
        stage.label,
        0,
        "This stage does not change the assessment on its own.",
    )


def _soil_type_factor(soil: SoilType, profile: CropProfile, stage_id: str | None) -> DecisionFactor:
    if soil == SoilType.UNKNOWN:
        return _factor(
            "soil_type",
            "Soil type",
            "Not provided",
            0,
            "Soil type affects how much water the soil can hold and how soon it runs short.",
            unknown=True,
        )
    label = soil.value.replace("_", " ").capitalize()
    low, high = SOIL_WATER_MM_PER_M[soil]
    holds = f"Holds about {low}-{high} mm of available water per metre of soil."
    stage = profile.stage(stage_id)
    first_irrigation = stage is not None and stage.id in profile.first_irrigation_stages
    if soil in _LIGHT_SOILS:
        text = f"{holds} Light soils run short sooner"
        if first_irrigation:
            text += ", and PAU advances the first irrigation on them."
        else:
            text += "."
        return _factor("soil_type", "Soil type", label, 1, text, "fao56_ch7", "pau_pop_rabi_2025")
    if soil in _HEAVY_SOILS and first_irrigation:
        return _factor(
            "soil_type",
            "Soil type",
            label,
            -1,
            f"{holds} PAU delays the first irrigation by a week on heavy paddy soils.",
            "fao56_ch7",
            "pau_pop_rabi_2025",
        )
    return _factor("soil_type", "Soil type", label, 0, holds, "fao56_ch7")


def _wind_factor(snapshot: WeatherSnapshot) -> DecisionFactor:
    speeds = [s for s in (snapshot.wind_speed_ms, snapshot.wind_max_24h_ms) if s is not None]
    if not speeds:
        return _factor(
            "wind", "Wind", "Not available", 0, "Wind speed is not available.", unknown=True
        )
    speed = max(speeds)
    value = f"up to {speed * 3.6:.0f} km/h"
    if speed >= WINDY_MS:
        return _factor(
            "wind",
            "Wind",
            value,
            -2,
            "PAU advises against irrigating on windy days, to avoid lodging.",
            "pau_pop_rabi_2025",
        )
    return _factor("wind", "Wind", value, 0, "Wind is not a concern for irrigating.")


def _schedule_factor(schedule, on_date: date) -> DecisionFactor | None:
    if schedule is None:
        return None
    if on_date > schedule.last_irrigation_by:
        return _factor(
            "schedule",
            "PAU timetable",
            f"Day {schedule.days_after_sowing} after sowing",
            -2,
            f"PAU's irrigation season for this sowing date ends on {schedule.last_irrigation_by:%d %B}.",
            "pau_pop_rabi_2025",
        )
    if schedule.in_window is not None:
        window = schedule.in_window
        return _factor(
            "schedule",
            "PAU timetable",
            f"Irrigation {window.number} window",
            1,
            f"Today falls in PAU's window for irrigation {window.number} ({window.basis}), if earlier "
            "irrigations ran on time.",
            "pau_pop_rabi_2025",
        )
    upcoming = schedule.next_window
    text = (
        f"PAU's next window is irrigation {upcoming.number}, from {upcoming.start_date:%d %B}."
        if upcoming
        else "All of PAU's scheduled irrigations for this sowing date have passed."
    )
    return _factor(
        "schedule",
        "PAU timetable",
        f"Day {schedule.days_after_sowing} after sowing",
        0,
        text,
        "pau_pop_rabi_2025",
    )


def _insufficient(
    inp: IrrigationInput, profile: CropProfile | None, reason: str, missing: list[str]
) -> IrrigationAssessment:
    stage = profile.stage(inp.growth_stage) if profile else None
    provenance = DataProvenance.UNAVAILABLE
    return IrrigationAssessment(
        crop=inp.crop,
        crop_name=profile.name if profile else inp.crop,
        growth_stage=stage.id if stage else inp.growth_stage,
        growth_stage_label=stage.label if stage else None,
        status=IrrigationStatus.INSUFFICIENT,
        action=IrrigationAction.CANNOT_ASSESS,
        headline="Not enough information to assess",
        summary=reason,
        next_action="Check the field yourself and try again once the missing information is available.",
        next_steps=[],
        factors=[],
        supporting_factors=[],
        missing_information=missing,
        limitations=[_LIMITATION_RULES],
        score=0,
        risk_level=RiskLevel.UNCERTAIN,
        confidence=Confidence.INSUFFICIENT,
        confidence_note="An assessment could not be made from the available information.",
        weather_provenance=provenance,
        sources=[],
    )


def assess_irrigation(
    inp: IrrigationInput, snapshot: WeatherSnapshot | None
) -> IrrigationAssessment:
    """Assess irrigation for one crop. Refuses to judge without validated weather."""
    profile = get_crop(inp.crop)
    if profile is None or profile.support != "rules_implemented":
        note = (
            profile.support_note if profile else f"{inp.crop} is not a crop FarmAgent recognises."
        )
        result = _insufficient(inp, profile, note, ["Crop-specific irrigation rules"])
        if snapshot is not None:
            result.weather_provenance = snapshot.provenance
        return result

    if snapshot is None or snapshot.provenance == DataProvenance.UNAVAILABLE:
        return _insufficient(
            inp,
            profile,
            "Verified weather could not be retrieved, so no weather-dependent assessment was made.",
            ["Verified weather for this location"],
        )

    on_date = inp.on_date or (snapshot.observed_at.date() if snapshot.observed_at else date.today())
    schedule = schedule_for_crop(profile.id, inp.sowing_date, on_date)

    soil_moisture = _soil_moisture_factor(inp.soil_moisture)
    forecast_rain = _forecast_rain_factor(snapshot, on_date)
    recent_rain = _recent_rain_factor(inp.recent_rainfall_mm, on_date)
    demand = _demand_factor(snapshot, profile, inp.growth_stage)
    stage_factor = _stage_factor(profile, inp.growth_stage)
    soil_type = _soil_type_factor(inp.soil_type, profile, inp.growth_stage)
    wind = _wind_factor(snapshot)
    schedule_factor = _schedule_factor(schedule, on_date)

    factors = [soil_moisture, forecast_rain, recent_rain, demand, stage_factor, soil_type, wind]
    if schedule_factor is not None:
        factors.append(schedule_factor)
    score = sum(f.weight for f in factors)

    stage = profile.stage(inp.growth_stage)
    season_over = stage is not None and stage.id in profile.no_irrigation_stages
    if schedule is not None and on_date > schedule.last_irrigation_by:
        season_over = True
    windy = wind.weight < 0
    rain_signal = forecast_rain.weight < 0
    rain_known = forecast_rain.direction != FactorDirection.UNKNOWN

    status, action, headline, next_action = _decide(
        inp.soil_moisture, score, windy, rain_signal, rain_known, season_over, snapshot.is_stale
    )

    # Soil moisture, stage and rain amount carry the decision. The rest refine it.
    critical_missing = []
    if inp.soil_moisture == SoilMoisture.UNKNOWN:
        critical_missing.append("Current soil moisture")
    if stage is None:
        critical_missing.append("Crop growth stage")
    if not rain_known:
        critical_missing.append("Forecast rainfall amount")
    secondary_missing = []
    if inp.soil_type == SoilType.UNKNOWN:
        secondary_missing.append("Soil type")
    if inp.recent_rainfall_mm is None:
        secondary_missing.append("Rain received in the last few days")
    if inp.sowing_date is None:
        secondary_missing.append("Sowing date")
    if inp.irrigation_method == IrrigationMethod.UNKNOWN:
        secondary_missing.append("Irrigation method")

    confidence, confidence_note = assess_confidence(
        snapshot, critical_missing=critical_missing, secondary_missing=secondary_missing
    )

    et_crop = None
    limitations = [_LIMITATION_RULES]
    if snapshot.et0_mm_day is not None and stage is not None and stage.kc is not None:
        et_crop = round(snapshot.et0_mm_day * stage.kc, 1)
        limitations.append(
            "Crop water use is a temperature-based Hargreaves estimate. FAO notes it should be "
            "checked regionally, and that it under-predicts in strong wind and over-predicts in "
            "high humidity. It is shown for context and does not affect the status."
        )
    if inp.irrigation_method == IrrigationMethod.RAINFED:
        limitations.append("This crop is recorded as rainfed, so irrigation may not be an option.")
    if inp.irrigation_method == IrrigationMethod.SPRINKLER and windy:
        limitations.append("Wind also reduces how evenly a sprinkler applies water.")
    if inp.soil_type in _LIGHT_SOILS and schedule is not None:
        limitations.append(
            "PAU's timetable is written for sandy loam or heavier soils, so lighter soils may need "
            "earlier irrigation than shown."
        )
    if schedule is not None:
        limitations.append(
            "The PAU windows assume earlier irrigations ran on time, and do not include any "
            "adjustment for rain."
        )
    if snapshot.warning:
        limitations.append(snapshot.warning)
    if snapshot.provenance == DataProvenance.SIMULATED:
        limitations.append("The weather in this assessment is simulated, not real.")

    summary = _summary(status, action, snapshot, forecast_rain, inp.soil_moisture)
    if action == IrrigationAction.CONSIDER_POSTPONING and rain_signal:
        summary = f"{summary} {_DECISION_DEPENDS}"

    source_ids: list[str] = [sid for f in factors for sid in f.source_ids]
    return IrrigationAssessment(
        crop=profile.id,
        crop_name=profile.name,
        growth_stage=stage.id if stage else inp.growth_stage,
        growth_stage_label=stage.label if stage else None,
        status=status,
        action=action,
        headline=headline,
        summary=summary,
        next_action=next_action,
        next_steps=_next_steps(action, inp.soil_moisture, rain_signal),
        factors=factors,
        supporting_factors=[
            f"{f.label}: {f.explanation}"
            for f in factors
            if f.direction
            in (FactorDirection.SUPPORTS_IRRIGATING, FactorDirection.AGAINST_IRRIGATING)
        ],
        missing_information=critical_missing + secondary_missing,
        limitations=limitations,
        score=score,
        risk_level=_risk_level(status, demand, inp.soil_moisture),
        confidence=confidence,
        confidence_note=confidence_note,
        estimated_crop_water_use_mm_day=et_crop,
        schedule=schedule,
        weather_provenance=snapshot.provenance,
        sources=resolve(source_ids),
    )


def _decide(
    moisture: SoilMoisture,
    score: int,
    windy: bool,
    rain_signal: bool,
    rain_known: bool,
    season_over: bool,
    stale: bool,
) -> tuple[IrrigationStatus, IrrigationAction, str, str]:
    if moisture == SoilMoisture.HIGH:
        return (
            IrrigationStatus.CAUTION,
            IrrigationAction.HOLD_IRRIGATION,
            "Hold irrigation: the soil is already wet",
            "Let the field drain, and check that water is not standing on it.",
        )
    if season_over:
        return (
            IrrigationStatus.MONITOR,
            IrrigationAction.HOLD_IRRIGATION,
            "Irrigation season has ended for this crop",
            "No irrigation is indicated. Plan for harvest timing instead.",
        )
    if windy:
        return (
            IrrigationStatus.CAUTION,
            IrrigationAction.CONSIDER_POSTPONING,
            "Wait for the wind to drop",
            "Hold off until a calm day, to avoid lodging.",
        )
    if rain_signal and score <= -1:
        return (
            IrrigationStatus.CAUTION,
            IrrigationAction.CONSIDER_POSTPONING,
            "Consider postponing irrigation",
            "Check soil moisture, then wait to see how much rain actually falls.",
        )
    if (
        moisture == SoilMoisture.LOW
        and not stale
        and rain_known
        and not rain_signal
        and (score >= FAVORABLE_MIN_SCORE)
    ):
        return (
            IrrigationStatus.FAVORABLE,
            IrrigationAction.CONSIDER_IRRIGATING,
            "Conditions support irrigating",
            "Confirm by checking the soil at root depth, then irrigate on a calm day.",
        )
    if moisture == SoilMoisture.LOW:
        return (
            IrrigationStatus.MONITOR,
            IrrigationAction.CHECK_SOIL_AND_REASSESS,
            "Soil is low, but the picture is mixed",
            "Recheck the forecast and your soil within a day. Irrigate if the rain does not come.",
        )
    if moisture == SoilMoisture.ADEQUATE:
        return (
            IrrigationStatus.MONITOR,
            IrrigationAction.CHECK_SOIL_AND_REASSESS,
            "No urgent need to irrigate",
            "Keep checking soil moisture over the next few days.",
        )
    return (
        IrrigationStatus.MONITOR,
        IrrigationAction.CHECK_SOIL_AND_REASSESS,
        "Check your soil before deciding",
        "Check soil moisture at root depth, then run this assessment again.",
    )


def _summary(
    status: IrrigationStatus,
    action: IrrigationAction,
    snapshot: WeatherSnapshot,
    rain: DecisionFactor,
    moisture: SoilMoisture,
) -> str:
    if status == IrrigationStatus.FAVORABLE:
        return (
            f"Soil moisture is low and little or no rain is forecast ({rain.value} over 48 hours), "
            "so the crop may be heading for water stress."
        )
    if action == IrrigationAction.CONSIDER_POSTPONING:
        if rain.weight < 0:
            return (
                f"Rain may do some of the work: {rain.value} is forecast over the next 48 hours. "
                "Probability and amount are both shown because neither is enough alone."
            )
        return "Strong wind is expected, and irrigating in wind raises the risk of lodging."
    if action == IrrigationAction.HOLD_IRRIGATION:
        if moisture == SoilMoisture.HIGH:
            return "You reported wet soil, and more water now risks waterlogging."
        return "The crop has passed the point in the season where irrigation is useful."
    if moisture == SoilMoisture.UNKNOWN:
        return (
            f"The weather alone cannot settle this. Forecast rain is {rain.value} over 48 hours, but "
            "without soil moisture FarmAgent will not call for irrigation."
        )
    if moisture == SoilMoisture.LOW:
        return (
            f"Soil moisture is low, but forecast rain ({rain.value}) or missing or out-of-date "
            "weather keeps this from being clear-cut."
        )
    return f"Soil moisture is adequate. Forecast rain is {rain.value} over 48 hours."


def _next_steps(action: IrrigationAction, moisture: SoilMoisture, rain_signal: bool) -> list[str]:
    steps: list[str] = []
    if moisture == SoilMoisture.UNKNOWN:
        steps.append("Check soil moisture by hand at root depth.")
    if action == IrrigationAction.CONSIDER_POSTPONING and rain_signal:
        steps.append("Measure the rain that actually falls, and reassess if little arrives.")
        steps.append("Review the forecast rainfall amount again tomorrow.")
    if action == IrrigationAction.CONSIDER_IRRIGATING:
        steps.append("Confirm the soil is dry at root depth before irrigating.")
        steps.append("Avoid windy days, and avoid applying more water than the crop needs.")
    if action == IrrigationAction.CHECK_SOIL_AND_REASSESS and moisture != SoilMoisture.UNKNOWN:
        steps.append("Reassess when the forecast changes or after any rain.")
    if action == IrrigationAction.HOLD_IRRIGATION and moisture == SoilMoisture.HIGH:
        steps.append("Drain standing water if you can, since wheat does not suit waterlogging.")
    return steps


def _risk_level(
    status: IrrigationStatus, demand: DecisionFactor, moisture: SoilMoisture
) -> RiskLevel:
    if status == IrrigationStatus.FAVORABLE:
        return RiskLevel.ELEVATED if demand.weight >= 2 else RiskLevel.MODERATE
    if status == IrrigationStatus.CAUTION:
        return RiskLevel.MODERATE
    if status == IrrigationStatus.INSUFFICIENT or moisture == SoilMoisture.UNKNOWN:
        return RiskLevel.UNCERTAIN
    return RiskLevel.LOW
