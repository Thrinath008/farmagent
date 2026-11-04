"""Shared types for the decision engine. No web framework, database or AI dependencies."""

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel

from app.schemas.weather import DataProvenance


class SoilMoisture(StrEnum):
    LOW = "low"
    ADEQUATE = "adequate"
    HIGH = "high"
    UNKNOWN = "unknown"


class SoilType(StrEnum):
    SANDY = "sandy"
    LOAMY_SAND = "loamy_sand"
    SANDY_LOAM = "sandy_loam"
    LOAM = "loam"
    SILT_LOAM = "silt_loam"
    CLAY_LOAM = "clay_loam"
    CLAY = "clay"
    UNKNOWN = "unknown"


class IrrigationMethod(StrEnum):
    FLOOD = "flood"
    BORDER = "border"
    FURROW = "furrow"
    SPRINKLER = "sprinkler"
    DRIP = "drip"
    RAINFED = "rainfed"
    UNKNOWN = "unknown"


class IrrigationStatus(StrEnum):
    """Rule-based labels. They are not scientifically calibrated measurements."""

    FAVORABLE = "favorable"
    MONITOR = "monitor"
    CAUTION = "caution"
    INSUFFICIENT = "insufficient_information"


class IrrigationAction(StrEnum):
    CONSIDER_IRRIGATING = "consider_irrigating"
    CONSIDER_POSTPONING = "consider_postponing"
    CHECK_SOIL_AND_REASSESS = "check_soil_and_reassess"
    HOLD_IRRIGATION = "hold_irrigation"
    CANNOT_ASSESS = "cannot_assess"


class RiskLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    ELEVATED = "elevated"
    UNCERTAIN = "uncertain"
    NOT_APPLICABLE = "not_applicable"


class Confidence(StrEnum):
    """How complete the inputs were. Never a measured accuracy."""

    INSUFFICIENT = "insufficient"
    LIMITED = "limited"
    MODERATE = "moderate"
    GOOD = "good"
    NOT_APPLICABLE = "not_applicable"


class FactorDirection(StrEnum):
    SUPPORTS_IRRIGATING = "supports_irrigating"
    AGAINST_IRRIGATING = "against_irrigating"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class Intent(StrEnum):
    IRRIGATION_ADVICE = "irrigation_advice"
    WEATHER_QUESTION = "weather_question"
    PEST_DISEASE_RISK = "pest_disease_risk"
    FIELD_OPERATION = "field_operation"
    CROP_GUIDANCE = "crop_guidance"
    FARM_BRIEFING = "farm_briefing"
    GENERAL = "general"
    OUT_OF_SCOPE = "out_of_scope"


WEATHER_DEPENDENT_INTENTS = frozenset(
    {
        Intent.IRRIGATION_ADVICE,
        Intent.WEATHER_QUESTION,
        Intent.PEST_DISEASE_RISK,
        Intent.FIELD_OPERATION,
        Intent.FARM_BRIEFING,
    }
)


class SourceRef(BaseModel):
    id: str
    title: str
    publisher: str
    url: str


class ForecastConditions(BaseModel):
    """One forecast period, in the terms the pest and disease rules evaluate."""

    time: datetime | None = None
    temperature_c: float
    humidity_pct: float
    rain_mm: float


class WeatherSnapshot(BaseModel):
    """The validated weather an assessment is allowed to use.

    Assessments read only this. Each value is None unless a weather provider supplied it, so
    "unknown" can never be mistaken for zero.
    """

    provenance: DataProvenance
    source: str
    observed_at: datetime | None = None
    is_stale: bool = False
    warning: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    description: str | None = None
    temperature_c: float | None = None
    feels_like_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_ms: float | None = None
    rain_last_1h_mm: float | None = None

    forecast_available: bool = False
    rain_next_24h_mm: float | None = None
    rain_next_48h_mm: float | None = None
    rain_prob_max_24h_pct: float | None = None
    rain_prob_max_48h_pct: float | None = None
    temp_max_48h_c: float | None = None
    temp_min_48h_c: float | None = None
    humidity_mean_48h_pct: float | None = None
    wind_max_24h_ms: float | None = None
    et0_mm_day: float | None = None
    periods: list[ForecastConditions] = []


class IrrigationWindow(BaseModel):
    number: int
    start_date: date
    end_date: date
    basis: str


class IrrigationSchedule(BaseModel):
    """PAU's timetable applied to a sowing date, assuming earlier irrigations ran on time."""

    sowing_date: date
    days_after_sowing: int
    windows: list[IrrigationWindow]
    last_irrigation_by: date
    next_window: IrrigationWindow | None = None
    in_window: IrrigationWindow | None = None
    source_id: str


class DecisionFactor(BaseModel):
    key: str
    label: str
    value: str
    direction: FactorDirection
    weight: int
    explanation: str
    source_ids: list[str] = []


class IrrigationAssessment(BaseModel):
    crop: str
    crop_name: str
    growth_stage: str | None = None
    growth_stage_label: str | None = None
    status: IrrigationStatus
    action: IrrigationAction
    headline: str
    summary: str
    next_action: str
    next_steps: list[str]
    factors: list[DecisionFactor]
    supporting_factors: list[str]
    missing_information: list[str]
    limitations: list[str]
    score: int
    risk_level: RiskLevel
    confidence: Confidence
    confidence_note: str
    estimated_crop_water_use_mm_day: float | None = None
    schedule: IrrigationSchedule | None = None
    weather_provenance: DataProvenance
    sources: list[SourceRef]


class PotentialRisk(BaseModel):
    id: str
    name: str
    category: str
    classification: RiskLevel
    favorable_conditions: str
    evidence: list[str]
    monitoring_actions: list[str]
    regional_note: str | None = None
    sources: list[SourceRef]


class EnvironmentalCondition(BaseModel):
    label: str
    value: str


class PestRiskAssessment(BaseModel):
    crop: str
    crop_name: str
    growth_stage: str | None = None
    growth_stage_label: str | None = None
    overall_classification: RiskLevel
    headline: str
    explanation: str
    risks: list[PotentialRisk]
    environmental_conditions: list[EnvironmentalCondition]
    crop_sensitivity: str
    missing_information: list[str]
    confidence: Confidence
    confidence_note: str
    disclaimer: str
    weather_provenance: DataProvenance


class WeatherContext(BaseModel):
    temperature_c: float | None = None
    humidity_pct: float | None = None
    rain_probability_pct: float | None = None
    expected_rain_mm: float | None = None
    window_hours: int = 48
    wind_speed_ms: float | None = None
    description: str | None = None
    location_name: str | None = None
    provenance: DataProvenance
    source: str
    observed_at: datetime | None = None
    is_stale: bool = False


class FarmingAdvice(BaseModel):
    """The one recommendation shape used by the agent, the engine and saved history."""

    intent: Intent
    recommendation: str | None = None
    summary: str
    reasoning: list[str] = []
    weather_context: WeatherContext | None = None
    risk_level: RiskLevel = RiskLevel.NOT_APPLICABLE
    confidence: Confidence = Confidence.NOT_APPLICABLE
    missing_information: list[str] = []
    next_steps: list[str] = []
    data_sources: list[str] = []
    requires_expert_verification: bool = False
    generated_by: str = "decision_engine"
