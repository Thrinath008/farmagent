"""Weather-based risk: uncertainty is reported, and nothing ever claims a diagnosis."""

import json

import pytest

from app.intelligence.pest_risk import DISCLAIMER, assess_pest_risk
from app.intelligence.recommendation import advice_from_pest_risk
from app.intelligence.types import Confidence, RiskLevel
from app.schemas.weather import DataProvenance
from tests.factories import period, snapshot


def yellow_rust_days(count: int) -> list:
    """Each day is 8 periods, with a 10 C minimum, a 20 C maximum, and humid hours."""
    day = [period(10, 90), period(12, 90), period(15, 70), period(20, 60)] * 2
    return day * count


def risk(assessment, risk_id):
    return next(r for r in assessment.risks if r.id == risk_id)


def test_sustained_pau_conditions_raise_yellow_rust():
    result = assess_pest_risk("wheat", "tillering", snapshot(periods=yellow_rust_days(3)))
    assert risk(result, "yellow_rust").classification == RiskLevel.ELEVATED
    assert result.overall_classification == RiskLevel.ELEVATED


def test_one_matching_day_is_moderate():
    periods = yellow_rust_days(1) + [period(25, 40)] * 8
    result = assess_pest_risk("wheat", "tillering", snapshot(periods=periods))
    assert risk(result, "yellow_rust").classification == RiskLevel.MODERATE


def test_warm_dry_forecast_does_not_raise_yellow_rust():
    result = assess_pest_risk("wheat", "tillering", snapshot(periods=[period(28, 35)] * 16))
    assert risk(result, "yellow_rust").classification == RiskLevel.LOW


def test_missing_humidity_is_uncertain_not_low():
    weather = snapshot(
        humidity_pct=None, humidity_mean_48h_pct=None, forecast_available=False, periods=[]
    )
    result = assess_pest_risk("wheat", "tillering", weather)
    assert result.overall_classification == RiskLevel.UNCERTAIN
    assert risk(result, "powdery_mildew").classification == RiskLevel.UNCERTAIN
    assert "Humidity" in result.missing_information
    assert result.confidence == Confidence.LIMITED
    assert "should not be read as all clear" in result.explanation


def test_single_reading_can_never_reach_elevated():
    weather = snapshot(temperature_c=21.0, humidity_pct=95.0, forecast_available=False, periods=[])
    result = assess_pest_risk("wheat", "tillering", weather)
    assert risk(result, "brown_rust").classification == RiskLevel.MODERATE
    assert all(r.classification != RiskLevel.ELEVATED for r in result.risks)


def test_daily_rule_with_too_little_forecast_is_uncertain():
    result = assess_pest_risk("wheat", "tillering", snapshot(periods=[period(10, 90)] * 3))
    assert risk(result, "yellow_rust").classification == RiskLevel.UNCERTAIN


def test_karnal_bunt_only_applies_at_flowering():
    rainy = [period(15, 90, rain=1.0)] * 16
    at_tillering = assess_pest_risk("wheat", "tillering", snapshot(periods=rainy))
    at_flowering = assess_pest_risk("wheat", "heading_flowering", snapshot(periods=rainy))
    assert risk(at_tillering, "karnal_bunt").classification == RiskLevel.LOW
    assert risk(at_flowering, "karnal_bunt").classification == RiskLevel.ELEVATED


def test_karnal_bunt_needs_rain_not_just_humidity():
    result = assess_pest_risk("wheat", "heading_flowering", snapshot(periods=[period(15, 90)] * 16))
    assert risk(result, "karnal_bunt").classification == RiskLevel.LOW


def test_brown_rust_counts_rain_as_free_moisture():
    result = assess_pest_risk(
        "wheat", "tillering", snapshot(periods=[period(22, 50, rain=1.0)] * 8)
    )
    assert risk(result, "brown_rust").classification == RiskLevel.ELEVATED


def test_aphids_have_no_weather_verdict_and_do_not_set_the_overall_result():
    result = assess_pest_risk("wheat", "heading_flowering", snapshot(periods=[period(28, 35)] * 40))
    aphids = risk(result, "aphids")
    assert aphids.classification == RiskLevel.UNCERTAIN
    assert any("5 aphids per ear head" in action for action in aphids.monitoring_actions)
    assert result.overall_classification == RiskLevel.LOW


def test_terminal_heat_applies_after_flowering_only():
    hot = [period(33, 30)] * 16
    late = assess_pest_risk("wheat", "grain_filling", snapshot(periods=hot))
    early = assess_pest_risk("wheat", "tillering", snapshot(periods=hot))
    assert risk(late, "terminal_heat").classification == RiskLevel.ELEVATED
    assert risk(early, "terminal_heat").classification == RiskLevel.LOW
    assert risk(early, "vegetative_heat").classification == RiskLevel.ELEVATED


def test_unknown_stage_is_flagged_and_limits_confidence():
    result = assess_pest_risk("wheat", None, snapshot(periods=[period(22, 90)] * 16))
    assert "Crop growth stage" in result.missing_information
    assert result.confidence == Confidence.LIMITED
    assert any("not checked" in line for line in risk(result, "brown_rust").evidence)


def test_confidence_never_reaches_good_without_field_data():
    result = assess_pest_risk("wheat", "tillering", snapshot(periods=[period(25, 50)] * 16))
    assert result.confidence == Confidence.MODERATE
    assert "Leaf wetness measurement" in result.missing_information


def test_no_weather_means_no_assessment():
    result = assess_pest_risk("wheat", "tillering", None)
    assert result.risks == []
    assert result.overall_classification == RiskLevel.UNCERTAIN
    assert result.confidence == Confidence.INSUFFICIENT
    assert result.disclaimer == DISCLAIMER


def test_crops_without_rules_are_not_assessed():
    result = assess_pest_risk("rice", "tillering", snapshot())
    assert result.risks == []
    assert "not implemented" in result.explanation


@pytest.mark.parametrize(
    "periods",
    [yellow_rust_days(3), [period(22, 90, rain=2.0)] * 16, [period(33, 30)] * 16, []],
)
def test_output_never_claims_a_diagnosis_or_prescribes_chemicals(periods):
    weather = snapshot(periods=periods)
    result = assess_pest_risk("wheat", "heading_flowering", weather)
    text = json.dumps(result.model_dump(mode="json")).lower()
    assert result.disclaimer == DISCLAIMER
    assert "not a plant disease diagnosis" in text
    for claim in ("has yellow rust", "is infected", "infestation detected", "you have"):
        assert claim not in text
    for chemical in ("propiconazole", "thiamethoxam", "potassium nitrate", "ml/acre", "g/acre"):
        assert chemical not in text


def test_explanations_of_raised_risk_say_it_does_not_mean_presence():
    result = assess_pest_risk("wheat", "tillering", snapshot(periods=yellow_rust_days(3)))
    assert "does not mean the problem is in your field" in result.explanation


def test_simulated_weather_is_carried_through():
    weather = snapshot(provenance=DataProvenance.SIMULATED, periods=[period(25, 50)] * 16)
    assert (
        assess_pest_risk("wheat", "tillering", weather).weather_provenance
        == DataProvenance.SIMULATED
    )


def test_advice_from_elevated_risk_asks_for_expert_verification():
    weather = snapshot(periods=yellow_rust_days(3))
    advice = advice_from_pest_risk(assess_pest_risk("wheat", "tillering", weather), weather)
    assert advice.requires_expert_verification is True
    assert DISCLAIMER in advice.summary
    assert advice.next_steps
