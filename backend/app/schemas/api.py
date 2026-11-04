"""Request and response models for the REST API."""

import json
import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.core.text import clean_text
from app.intelligence.crops import get_crop
from app.intelligence.types import (
    FarmingAdvice,
    IrrigationAssessment,
    IrrigationMethod,
    IrrigationSchedule,
    PestRiskAssessment,
    SoilMoisture,
    SoilType,
    SourceRef,
    WeatherSnapshot,
)

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
AreaUnit = Literal["acre", "hectare", "kanal", "bigha"]
Latitude = Annotated[float, Field(ge=-90, le=90)]
Longitude = Annotated[float, Field(ge=-180, le=180)]


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Response(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# Session


class UserRead(_Response):
    id: uuid.UUID
    display_name: str | None
    preferred_language: str
    created_at: datetime


class GuestSessionResponse(BaseModel):
    token: str = Field(description="Shown once. Send it as the X-Guest-Token header.")
    user: UserRead


class UserUpdate(_Request):
    display_name: ShortText | None = None
    preferred_language: ShortText | None = None


# Farms


class FarmCropCreate(_Request):
    crop: str = Field(min_length=1, max_length=40)
    variety: ShortText | None = None
    sowing_date: date | None = None
    growth_stage: str | None = Field(default=None, max_length=40)
    irrigation_method: IrrigationMethod | None = None

    @model_validator(mode="after")
    def _check_crop_and_stage(self):
        profile = get_crop(self.crop)
        if profile is None:
            raise ValueError("This crop is not in FarmAgent's catalogue.")
        self.crop = profile.id
        if self.growth_stage and profile.stages:
            stage = profile.stage(self.growth_stage)
            if stage is None:
                raise ValueError(f"'{self.growth_stage}' is not a growth stage of {profile.name}.")
            self.growth_stage = stage.id
        return self


class FarmCropUpdate(_Request):
    variety: ShortText | None = None
    sowing_date: date | None = None
    growth_stage: str | None = Field(default=None, max_length=40)
    irrigation_method: IrrigationMethod | None = None


class FarmCropRead(_Response):
    id: uuid.UUID
    farm_id: uuid.UUID
    crop: str
    crop_name: str = ""
    support_level: str = "planned"
    variety: str | None
    sowing_date: date | None
    growth_stage: str | None
    growth_stage_label: str | None = None
    irrigation_method: str | None
    irrigation_schedule: IrrigationSchedule | None = None
    created_at: datetime


class _FarmFields(_Request):
    name: ShortText | None = None
    location_name: ShortText | None = None
    state: ShortText | None = None
    country: ShortText | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    size_value: float | None = Field(default=None, gt=0, le=1_000_000)
    area_unit: AreaUnit | None = None
    soil_type: SoilType | None = None

    @model_validator(mode="after")
    def _coordinates_come_in_pairs(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or neither.")
        return self


class FarmCreate(_FarmFields):
    crops: list[FarmCropCreate] = Field(default_factory=list, max_length=20)


class FarmUpdate(_FarmFields):
    pass


class FarmRead(_Response):
    id: uuid.UUID
    name: str | None
    location_name: str | None
    state: str | None
    country: str | None
    latitude: float | None
    longitude: float | None
    size_value: float | None
    area_unit: str | None
    soil_type: str | None
    crops: list[FarmCropRead] = []
    created_at: datetime
    updated_at: datetime


# Crop catalogue


class StageRead(BaseModel):
    id: str
    label: str
    irrigation_critical: bool
    note: str | None = None


class CropRead(BaseModel):
    id: str
    name: str
    support_level: str
    support_note: str
    stages: list[StageRead]
    irrigation_considerations: list[str]
    sources: list[SourceRef]


class CatalogResponse(BaseModel):
    crops: list[CropRead]
    soil_types: list[str]
    irrigation_methods: list[str]
    soil_moisture_levels: list[str]
    area_units: list[str]


# Assessments


class ApiIssue(BaseModel):
    code: str
    message: str


class AssessmentTarget(_Request):
    """Where and what to assess. Explicit values override what is stored on the farm."""

    farm_id: uuid.UUID | None = None
    farm_crop_id: uuid.UUID | None = None
    latitude: Latitude | None = None
    longitude: Longitude | None = None
    crop: str | None = Field(default=None, max_length=40)
    growth_stage: str | None = Field(default=None, max_length=40)
    force_refresh: bool = False

    @model_validator(mode="after")
    def _coordinates_come_in_pairs(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Provide both latitude and longitude, or neither.")
        return self


class IrrigationRequest(AssessmentTarget):
    soil_type: SoilType | None = None
    soil_moisture: SoilMoisture = SoilMoisture.UNKNOWN
    irrigation_method: IrrigationMethod | None = None
    recent_rainfall_mm: float | None = Field(default=None, ge=0, le=1000)
    sowing_date: date | None = None


class PestRiskRequest(AssessmentTarget):
    pass


class IrrigationResponse(BaseModel):
    assessment: IrrigationAssessment
    advice: FarmingAdvice
    weather: WeatherSnapshot | None
    weather_issues: list[ApiIssue] = []
    farm_id: uuid.UUID | None = None


class PestRiskResponse(BaseModel):
    assessment: PestRiskAssessment
    advice: FarmingAdvice
    weather: WeatherSnapshot | None
    weather_issues: list[ApiIssue] = []
    farm_id: uuid.UUID | None = None


# Agent


class ChatRequest(_Request):
    message: str = Field(min_length=1, max_length=20000)
    conversation_id: uuid.UUID | None = None
    farm_id: uuid.UUID | None = None

    @field_validator("message")
    @classmethod
    def _clean_message(cls, value: str) -> str:
        cleaned = clean_text(value)
        if not cleaned:
            raise ValueError("The message is empty.")
        return cleaned


class ToolLogEntry(BaseModel):
    name: str
    input: dict = {}
    ok: bool
    duration_ms: int
    error_code: str | None = None
    provenance: str | None = None


class ChatResponse(BaseModel):
    conversation_id: uuid.UUID
    message_id: uuid.UUID
    advice: FarmingAdvice
    tool_log: list[ToolLogEntry]
    saved_recommendation_ids: list[str] = []


class AnalyzeRequest(_Request):
    farm_id: uuid.UUID
    farm_crop_id: uuid.UUID | None = None
    focus: str | None = Field(default=None, max_length=500)


class AnalyzeResponse(BaseModel):
    advice: FarmingAdvice
    tool_log: list[ToolLogEntry]


# Conversations


class ConversationCreate(_Request):
    title: ShortText | None = None
    farm_id: uuid.UUID | None = None


class ConversationRead(_Response):
    id: uuid.UUID
    farm_id: uuid.UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


class MessageRead(_Response):
    id: uuid.UUID
    role: str
    content: str
    advice: FarmingAdvice | None = None
    tool_log: list[ToolLogEntry] | None = None
    created_at: datetime


class ConversationDetail(ConversationRead):
    messages: list[MessageRead]


# Recommendations


class RecommendationCreate(_Request):
    advice: FarmingAdvice
    origin: Literal["assistant", "irrigation_advisor", "crop_health", "scenario_lab"]
    farm_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    crop: str | None = Field(default=None, max_length=40)
    latitude: Latitude | None = None
    longitude: Longitude | None = None

    @field_validator("advice")
    @classmethod
    def _bounded(cls, advice: FarmingAdvice) -> FarmingAdvice:
        if len(json.dumps(advice.model_dump(mode="json"))) > 20_000:
            raise ValueError("This recommendation is too large to save.")
        return advice


class RecommendationRead(_Response):
    id: uuid.UUID
    farm_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    origin: str
    intent: str
    crop: str | None
    recommendation: str | None
    summary: str
    risk_level: str
    confidence: str
    advice: FarmingAdvice
    weather_provenance: str | None
    weather_observed_at: datetime | None
    created_at: datetime


# Scenarios


class ScenarioInputs(BaseModel):
    temperature_c: float
    humidity_pct: float
    rain_probability_pct: float
    expected_rain_mm: float
    wind_speed_ms: float
    crop: str
    growth_stage: str
    soil_moisture: SoilMoisture


class ScenarioDefinition(BaseModel):
    id: str
    title: str
    description: str
    inputs: ScenarioInputs


class ScenarioRunRequest(_Request):
    scenario_ids: list[Literal["A", "B"]] = Field(default=["A", "B"], min_length=1, max_length=2)
    include_ai: bool = False


class ScenarioAiResult(BaseModel):
    status: Literal["completed", "unavailable", "not_requested"]
    advice: FarmingAdvice | None = None
    tool_log: list[ToolLogEntry] = []
    message: str | None = None
    code: str | None = None


class ScenarioResult(BaseModel):
    definition: ScenarioDefinition
    provenance: Literal["simulated"] = "simulated"
    assessment: IrrigationAssessment
    pest_risk: PestRiskAssessment
    advice: FarmingAdvice
    ai: ScenarioAiResult


class InputDifference(BaseModel):
    key: str
    label: str
    values: dict[str, str]
    differs: bool


class FactorComparison(BaseModel):
    key: str
    label: str
    values: dict[str, str]
    weights: dict[str, int]
    explanations: dict[str, str]


class ScenarioRunResponse(BaseModel):
    label: str = "SIMULATED DATA"
    notice: str
    results: list[ScenarioResult]
    input_differences: list[InputDifference]
    factor_comparison: list[FactorComparison]
    outcomes_differ: bool


# Health


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    environment: str
    database: Literal["ok", "unavailable"]
    weather_configured: bool
    ai_configured: bool
    ai_model: str | None
