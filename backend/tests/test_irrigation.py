"""The irrigation engine: mandatory scenarios, honesty about gaps, and the PAU rules."""

from datetime import date

import pytest

from app.intelligence.growth_stages import rain_interval_extension_days, wheat_irrigation_schedule
from app.intelligence.irrigation import IrrigationInput, assess_irrigation
from app.intelligence.types import (
    Confidence,
    FactorDirection,
    IrrigationAction,
    IrrigationMethod,
    IrrigationStatus,
    RiskLevel,
    SoilMoisture,
    SoilType,
)
from app.intelligence.weather_analysis import extraterrestrial_radiation_mj, hargreaves_et0
from app.schemas.weather import DataProvenance
from tests.factories import snapshot

ON = date(2027, 1, 15)

RAINY = dict(
    temperature_c=24.0,
    humidity_pct=80.0,
    humidity_mean_48h_pct=80.0,
    temp_max_48h_c=24.0,
    rain_next_48h_mm=15.0,
    rain_prob_max_48h_pct=85.0,
)
HOT_DRY = dict(
    temperature_c=36.0,
    humidity_pct=30.0,
    humidity_mean_48h_pct=30.0,
    temp_max_48h_c=36.0,
    rain_next_48h_mm=0.0,
    rain_prob_max_48h_pct=5.0,
)


def assess(weather=None, **fields):
    fields.setdefault("crop", "wheat")
    fields.setdefault("growth_stage", "vegetative")
    fields.setdefault("on_date", ON)
    return assess_irrigation(
        IrrigationInput(**fields), weather if weather is not None else snapshot()
    )


def factor(assessment, key):
    return next(f for f in assessment.factors if f.key == key)


def test_rainy_conditions_lead_to_considering_postponement():
    result = assess(snapshot(**RAINY))
    assert result.status == IrrigationStatus.CAUTION
    assert result.action == IrrigationAction.CONSIDER_POSTPONING
    assert factor(result, "forecast_rain").direction == FactorDirection.AGAINST_IRRIGATING
    assert "soil moisture" in result.summary
    assert "how much rain actually falls" in result.summary


def test_hot_and_dry_with_low_soil_supports_irrigating():
    result = assess(snapshot(**HOT_DRY), soil_moisture=SoilMoisture.LOW)
    assert result.status == IrrigationStatus.FAVORABLE
    assert result.action == IrrigationAction.CONSIDER_IRRIGATING
    assert result.risk_level == RiskLevel.ELEVATED
    assert factor(result, "water_demand").weight == 2
    assert factor(result, "soil_moisture").weight == 3


def test_missing_soil_moisture_is_named_and_limits_confidence():
    result = assess(snapshot(**RAINY))
    assert "Current soil moisture" in result.missing_information
    assert result.confidence == Confidence.LIMITED
    assert factor(result, "soil_moisture").direction == FactorDirection.UNKNOWN


def test_hot_and_dry_without_soil_moisture_will_not_call_for_irrigation():
    result = assess(snapshot(**HOT_DRY))
    assert result.status == IrrigationStatus.MONITOR
    assert result.action == IrrigationAction.CHECK_SOIL_AND_REASSESS
    assert result.confidence == Confidence.LIMITED


def test_temperature_alone_is_never_enough():
    weather = snapshot(
        temperature_c=44.0,
        humidity_pct=None,
        humidity_mean_48h_pct=None,
        temp_max_48h_c=44.0,
        rain_next_48h_mm=None,
        rain_prob_max_48h_pct=None,
        forecast_available=False,
    )
    result = assess(weather)
    assert result.status != IrrigationStatus.FAVORABLE
    assert result.action != IrrigationAction.CONSIDER_IRRIGATING


def test_rain_probability_without_an_amount_does_not_postpone():
    result = assess(snapshot(rain_next_48h_mm=None, rain_prob_max_48h_pct=95.0))
    assert result.action != IrrigationAction.CONSIDER_POSTPONING
    assert factor(result, "forecast_rain").direction == FactorDirection.UNKNOWN
    assert "Forecast rainfall amount" in result.missing_information


def test_high_probability_of_a_trivial_amount_does_not_postpone():
    result = assess(snapshot(rain_next_48h_mm=0.5, rain_prob_max_48h_pct=90.0))
    assert result.action != IrrigationAction.CONSIDER_POSTPONING
    assert factor(result, "forecast_rain").weight == 0


def test_large_amount_at_low_probability_does_not_postpone():
    result = assess(snapshot(rain_next_48h_mm=20.0, rain_prob_max_48h_pct=20.0))
    assert factor(result, "forecast_rain").weight == 0


def test_low_soil_with_rain_coming_stays_mixed_not_favorable():
    weather = snapshot(**{**RAINY, "temperature_c": 20.0, "temp_max_48h_c": 20.0})
    result = assess(weather, soil_moisture=SoilMoisture.LOW)
    assert result.status != IrrigationStatus.FAVORABLE


def test_no_weather_gives_insufficient_information():
    result = assess_irrigation(IrrigationInput(crop="wheat", soil_moisture=SoilMoisture.LOW), None)
    assert result.status == IrrigationStatus.INSUFFICIENT
    assert result.action == IrrigationAction.CANNOT_ASSESS
    assert result.confidence == Confidence.INSUFFICIENT
    assert "Verified weather for this location" in result.missing_information
    assert result.factors == []


@pytest.mark.parametrize("crop", ["rice", "maize", "cotton", "sugarcane", "pulses", "vegetables"])
def test_crops_without_rules_are_not_assessed(crop):
    result = assess(snapshot(**HOT_DRY), crop=crop, soil_moisture=SoilMoisture.LOW)
    assert result.status == IrrigationStatus.INSUFFICIENT
    assert "not implemented" in result.summary


def test_unknown_crop_is_not_assessed():
    assert assess(crop="dragonfruit").status == IrrigationStatus.INSUFFICIENT


def test_stale_weather_cannot_support_irrigating_and_limits_confidence():
    weather = snapshot(**HOT_DRY, is_stale=True, provenance=DataProvenance.CACHED)
    result = assess(weather, soil_moisture=SoilMoisture.LOW)
    assert result.status != IrrigationStatus.FAVORABLE
    assert result.confidence == Confidence.LIMITED


def test_wind_holds_back_irrigation_even_when_otherwise_favorable():
    result = assess(snapshot(**HOT_DRY, wind_max_24h_ms=11.0), soil_moisture=SoilMoisture.LOW)
    assert result.status == IrrigationStatus.CAUTION
    assert result.action == IrrigationAction.CONSIDER_POSTPONING
    assert "lodging" in factor(result, "wind").explanation


def test_wet_soil_holds_irrigation():
    result = assess(snapshot(**HOT_DRY), soil_moisture=SoilMoisture.HIGH)
    assert result.status == IrrigationStatus.CAUTION
    assert result.action == IrrigationAction.HOLD_IRRIGATION


def test_maturity_holds_irrigation():
    result = assess(growth_stage="maturity", soil_moisture=SoilMoisture.LOW)
    assert result.action == IrrigationAction.HOLD_IRRIGATION


def test_after_pau_season_end_holds_irrigation():
    result = assess(
        soil_moisture=SoilMoisture.LOW, sowing_date=date(2026, 11, 10), on_date=date(2027, 4, 5)
    )
    assert result.action == IrrigationAction.HOLD_IRRIGATION


def test_adequate_soil_means_no_urgency():
    result = assess(soil_moisture=SoilMoisture.ADEQUATE)
    assert result.status == IrrigationStatus.MONITOR
    assert result.risk_level == RiskLevel.LOW


def test_recent_rain_uses_the_pau_interval_rule():
    result = assess(recent_rainfall_mm=20.0)
    recent = factor(result, "recent_rain")
    assert recent.weight == -2
    assert "10 days" in recent.explanation


def test_light_soil_points_towards_irrigating_and_cites_fao():
    result = assess(soil_type=SoilType.SANDY)
    soil = factor(result, "soil_type")
    assert soil.weight == 1
    assert "fao56_ch7" in soil.source_ids
    assert "50-110 mm" in soil.explanation


def test_heavy_soil_delays_only_the_first_irrigation():
    assert (
        factor(
            assess(soil_type=SoilType.CLAY, growth_stage="crown_root_initiation"), "soil_type"
        ).weight
        == -1
    )
    assert factor(assess(soil_type=SoilType.CLAY, growth_stage="jointing"), "soil_type").weight == 0


def test_critical_stage_weighs_towards_irrigating():
    assert factor(assess(growth_stage="heading_flowering"), "growth_stage").weight == 1
    assert factor(assess(growth_stage="jointing"), "growth_stage").weight == 0


def test_stage_aliases_resolve():
    assert assess(growth_stage="CRI").growth_stage == "crown_root_initiation"
    assert assess(growth_stage="Flowering").growth_stage == "heading_flowering"


def test_unrecognised_stage_counts_as_missing():
    result = assess(growth_stage="purple")
    assert "Crop growth stage" in result.missing_information


def test_complete_inputs_reach_good_confidence():
    result = assess(
        soil_moisture=SoilMoisture.ADEQUATE,
        soil_type=SoilType.LOAM,
        irrigation_method=IrrigationMethod.FLOOD,
        recent_rainfall_mm=0.0,
        sowing_date=date(2026, 11, 10),
    )
    assert result.confidence == Confidence.GOOD
    assert result.missing_information == []
    assert "not a measured accuracy" in result.confidence_note


def test_simulated_weather_is_declared_in_the_result():
    result = assess(snapshot(**RAINY, provenance=DataProvenance.SIMULATED))
    assert result.weather_provenance == DataProvenance.SIMULATED
    assert any("simulated" in line for line in result.limitations)


def test_labels_are_declared_uncalibrated():
    assert any("not scientifically calibrated" in line for line in assess().limitations)


def test_same_inputs_give_identical_results():
    first = assess(snapshot(**RAINY))
    second = assess(snapshot(**RAINY))
    assert first.model_dump() == second.model_dump()


def test_cited_sources_are_real_entries_with_urls():
    result = assess(snapshot(**RAINY))
    assert result.sources
    assert all(source.url.startswith("https://") for source in result.sources)


def test_crop_water_use_estimate_is_informational_only():
    with_et = assess(snapshot(et0_mm_day=4.0), growth_stage="heading_flowering")
    without_et = assess(snapshot(et0_mm_day=None), growth_stage="heading_flowering")
    assert with_et.estimated_crop_water_use_mm_day == 4.6
    assert without_et.estimated_crop_water_use_mm_day is None
    assert with_et.status == without_et.status
    assert with_et.score == without_et.score


# PAU timetable


def centre(window):
    return window.start_date + (window.end_date - window.start_date) / 2


def test_october_sowing_gets_first_irrigation_at_three_weeks():
    schedule = wheat_irrigation_schedule(date(2026, 10, 25), date(2026, 11, 1))
    assert centre(schedule.windows[0]) == date(2026, 11, 15)


def test_november_sowing_gets_first_irrigation_at_four_weeks():
    schedule = wheat_irrigation_schedule(date(2026, 11, 10), date(2026, 11, 20))
    assert centre(schedule.windows[0]) == date(2026, 12, 8)
    assert (schedule.windows[0].end_date - schedule.windows[0].start_date).days == 6


@pytest.mark.parametrize(
    ("sowing", "bases"),
    [
        (date(2026, 11, 21), ["5-6 weeks", "5-6 weeks", "4 weeks"]),
        (date(2026, 11, 22), ["5-6 weeks", "3-4 weeks", "2 weeks"]),
        (date(2026, 12, 20), ["5-6 weeks", "3-4 weeks", "2 weeks"]),
        (date(2026, 12, 21), ["4 weeks", "3 weeks", "2 weeks"]),
        (date(2027, 1, 15), ["4 weeks", "3 weeks", "2 weeks"]),
    ],
)
def test_later_irrigations_follow_the_pau_table(sowing, bases):
    schedule = wheat_irrigation_schedule(sowing, sowing)
    assert [w.basis.split(" after")[0] for w in schedule.windows[1:]] == bases


@pytest.mark.parametrize("sowing", [date(2027, 1, 16), date(2026, 9, 15), date(2026, 6, 1)])
def test_sowing_outside_the_published_windows_has_no_schedule(sowing):
    assert wheat_irrigation_schedule(sowing, sowing) is None


def test_season_end_depends_on_sowing_date():
    timely = wheat_irrigation_schedule(date(2026, 11, 10), date(2026, 11, 20))
    late = wheat_irrigation_schedule(date(2026, 12, 10), date(2026, 12, 20))
    january = wheat_irrigation_schedule(date(2027, 1, 5), date(2027, 1, 10))
    assert timely.last_irrigation_by == date(2027, 3, 31)
    assert late.last_irrigation_by == date(2027, 4, 10)
    assert january.last_irrigation_by == date(2027, 4, 10)


def test_schedule_reports_where_today_falls():
    inside = wheat_irrigation_schedule(date(2026, 11, 10), date(2026, 12, 8))
    assert inside.in_window.number == 1
    assert inside.next_window.number == 2
    assert inside.days_after_sowing == 28
    between = wheat_irrigation_schedule(date(2026, 11, 10), date(2026, 12, 25))
    assert between.in_window is None
    assert between.next_window.number == 2


def test_being_inside_a_window_weighs_towards_irrigating():
    result = assess(sowing_date=date(2026, 11, 10), on_date=date(2026, 12, 8))
    assert factor(result, "schedule").weight == 1
    assert "irrigation 1" in factor(result, "schedule").explanation


@pytest.mark.parametrize(
    ("rain", "on_date", "days"),
    [
        (10, date(2027, 1, 31), 5),
        (10, date(2027, 2, 1), 2),
        (15, date(2027, 1, 15), 7.5),
        (10, date(2026, 12, 15), 5),
    ],
)
def test_rain_extends_the_interval_per_pau(rain, on_date, days):
    assert rain_interval_extension_days(rain, on_date) == days


# Hargreaves


def test_extraterrestrial_radiation_matches_fao_worked_example():
    # FAO-56 Example 8: 20 degrees south on 3 September gives Ra = 32.2 MJ/m2/day.
    assert extraterrestrial_radiation_mj(-20, date(2027, 9, 3)) == pytest.approx(32.2, abs=0.1)


def test_hargreaves_rises_with_diurnal_range_and_rejects_bad_input():
    narrow = hargreaves_et0(15, 20, 30.9, date(2027, 2, 1))
    wide = hargreaves_et0(10, 25, 30.9, date(2027, 2, 1))
    assert 0 < narrow < wide
    assert hargreaves_et0(25, 10, 30.9, date(2027, 2, 1)) is None
