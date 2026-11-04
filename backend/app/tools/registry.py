"""The seven agent tools. Handlers run on the backend and only return validated results."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import AppError, LocationNotFoundError
from app.intelligence.crops import get_crop
from app.intelligence.growth_stages import schedule_for_crop, stage_information
from app.intelligence.irrigation import IrrigationInput, assess_irrigation
from app.intelligence.pest_risk import assess_pest_risk
from app.intelligence.recommendation import weather_context_from_snapshot
from app.intelligence.sources import resolve
from app.intelligence.types import (
    Confidence,
    FarmingAdvice,
    Intent,
    IrrigationMethod,
    RiskLevel,
    SoilMoisture,
    SoilType,
)
from app.schemas.weather import GeocodeResult
from app.services.assessments import load_weather
from app.services.recommendations import save_advice
from app.tools.base import Tool, ToolContext, ToolRefusedError, ToolRegistry


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _Coordinates(_Strict):
    latitude: float = Field(ge=-90, le=90, description="Latitude in decimal degrees.")
    longitude: float = Field(ge=-180, le=180, description="Longitude in decimal degrees.")


class CurrentWeatherInput(_Coordinates):
    pass


class ForecastInput(_Coordinates):
    horizon_hours: int = Field(
        default=48, ge=3, le=120, description="How many hours ahead to return, up to 120."
    )


class CropInformationInput(_Strict):
    crop: str = Field(min_length=1, max_length=40, description="Crop name, for example wheat.")
    variety: str | None = Field(default=None, max_length=80)
    growth_stage: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=160)
    sowing_date: date | None = Field(
        default=None, description="If known. Returns PAU's irrigation timetable for wheat."
    )


class IrrigationNeedInput(_Coordinates):
    crop: str = Field(min_length=1, max_length=40)
    growth_stage: str | None = Field(default=None, max_length=40)
    soil_type: SoilType = SoilType.UNKNOWN
    soil_moisture: SoilMoisture = Field(
        default=SoilMoisture.UNKNOWN, description="Only as stated by the farmer. Never guess."
    )
    irrigation_method: IrrigationMethod = IrrigationMethod.UNKNOWN
    recent_rainfall_mm: float | None = Field(
        default=None, ge=0, le=1000, description="Rain the farmer says fell in recent days, in mm."
    )
    sowing_date: date | None = None


class PestRiskInput(_Coordinates):
    crop: str = Field(min_length=1, max_length=40)
    growth_stage: str | None = Field(default=None, max_length=40)
    location: str | None = Field(default=None, max_length=160)


class LocationInput(_Strict):
    query: str | None = Field(
        default=None, min_length=2, max_length=160, description="A place name to look up."
    )
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def _needs_a_target(self):
        has_coordinates = self.latitude is not None and self.longitude is not None
        if not self.query and not has_coordinates:
            raise ValueError("Provide either query, or both latitude and longitude.")
        return self


class SaveRecommendationInput(_Strict):
    intent: Intent
    recommendation: str = Field(min_length=1, max_length=2000)
    summary: str = Field(min_length=1, max_length=4000)
    reasoning: list[str] = Field(default_factory=list, max_length=20)
    risk_level: RiskLevel = RiskLevel.NOT_APPLICABLE
    confidence: Confidence = Confidence.LIMITED
    next_steps: list[str] = Field(default_factory=list, max_length=20)
    crop: str | None = Field(default=None, max_length=40)


class LocationInformation(BaseModel):
    matches: list[GeocodeResult]
    data_source: str = "OpenWeatherMap Geocoding"


class CropInformation(BaseModel):
    crop: str
    name: str
    support_level: str
    support_note: str
    variety_note: str | None = None
    growth_stage: dict | None = None
    available_stages: list[str]
    irrigation_considerations: list[str]
    weather_sensitivities: list[str]
    irrigation_schedule: dict | None = None
    sources: list[dict]


async def _get_current_weather(args: CurrentWeatherInput, ctx: ToolContext):
    weather = await ctx.weather.get_current(args.latitude, args.longitude)
    ctx.ledger.current = weather
    return weather


async def _get_weather_forecast(args: ForecastInput, ctx: ToolContext):
    forecast = await ctx.weather.get_forecast(
        args.latitude, args.longitude, horizon_hours=args.horizon_hours
    )
    ctx.ledger.forecast = forecast
    return forecast


async def _get_crop_information(args: CropInformationInput, ctx: ToolContext):
    profile = get_crop(args.crop)
    if profile is None:
        raise ToolRefusedError(f"'{args.crop}' is not a crop FarmAgent knows about.")
    ctx.used_crop_knowledge = True
    info = stage_information(profile, args.growth_stage)
    variety_note = None
    if args.variety:
        variety_note = profile.variety_notes.get(
            args.variety.strip().lower(),
            "No variety-specific rules are implemented for this variety.",
        )
    schedule = schedule_for_crop(profile.id, args.sowing_date, date.today())
    return CropInformation(
        crop=profile.id,
        name=profile.name,
        support_level=profile.support,
        support_note=profile.support_note,
        variety_note=variety_note,
        growth_stage=info.model_dump() if info else None,
        available_stages=[s.id for s in profile.stages],
        irrigation_considerations=list(profile.irrigation_considerations),
        weather_sensitivities=list(profile.weather_sensitivities),
        irrigation_schedule=schedule.model_dump(mode="json") if schedule else None,
        sources=[s.model_dump() for s in resolve(profile.source_ids)],
    )


async def _fetch_for_assessment(latitude: float, longitude: float, ctx: ToolContext):
    bundle = await load_weather(ctx.weather, latitude, longitude)
    if bundle.current is not None:
        ctx.ledger.current = bundle.current
    if bundle.forecast is not None:
        ctx.ledger.forecast = bundle.forecast
    ctx.ledger.failures.extend(error.code for error in bundle.errors)
    ctx.used_engine = True
    return bundle


async def _assess_irrigation_need(args: IrrigationNeedInput, ctx: ToolContext):
    bundle = await _fetch_for_assessment(args.latitude, args.longitude, ctx)
    return assess_irrigation(
        IrrigationInput(
            crop=args.crop,
            growth_stage=args.growth_stage,
            soil_type=args.soil_type,
            soil_moisture=args.soil_moisture,
            irrigation_method=args.irrigation_method,
            recent_rainfall_mm=args.recent_rainfall_mm,
            sowing_date=args.sowing_date,
        ),
        bundle.snapshot,
    )


async def _assess_weather_pest_risk(args: PestRiskInput, ctx: ToolContext):
    bundle = await _fetch_for_assessment(args.latitude, args.longitude, ctx)
    return assess_pest_risk(args.crop, args.growth_stage, bundle.snapshot)


async def _get_location_information(args: LocationInput, ctx: ToolContext):
    if args.query:
        matches = await ctx.weather.geocode(args.query)
    else:
        matches = await ctx.weather.reverse_geocode(args.latitude, args.longitude)
    if not matches:
        raise LocationNotFoundError()
    try:
        # The geocoder has no timezone. The weather feed does, so add it for the best match.
        weather = await ctx.weather.get_current(matches[0].latitude, matches[0].longitude)
        matches[0].timezone_offset_seconds = weather.timezone_offset_seconds
    except AppError:
        pass  # The place was found. Only the optional timezone is missing.
    return LocationInformation(matches=matches)


async def _save_recommendation(args: SaveRecommendationInput, ctx: ToolContext):
    if not ctx.allow_save:
        raise ToolRefusedError(
            "The farmer has not asked to save anything in this message. Offer to save it instead."
        )
    if ctx.session_factory is None or ctx.user_id is None:
        raise ToolRefusedError("Saving is not available here.")
    snapshot = ctx.ledger.snapshot()
    advice = FarmingAdvice(
        intent=args.intent,
        recommendation=args.recommendation,
        summary=args.summary,
        reasoning=args.reasoning,
        weather_context=weather_context_from_snapshot(snapshot) if snapshot else None,
        risk_level=args.risk_level,
        confidence=args.confidence,
        next_steps=args.next_steps,
        data_sources=[snapshot.source] if snapshot else [],
        generated_by="claude_agent",
    )
    async with ctx.session_factory() as session:
        saved = await save_advice(
            session,
            user_id=ctx.user_id,
            advice=advice,
            origin=ctx.origin,
            farm_id=ctx.farm_id,
            conversation_id=ctx.conversation_id,
            crop=args.crop,
        )
        await session.commit()
    ctx.saved_recommendation_ids.append(str(saved.id))
    return {"saved": True, "recommendation_id": str(saved.id)}


def build_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            Tool(
                "get_current_weather",
                "Get validated current weather for coordinates: temperature, feels-like, humidity, "
                "conditions, wind, cloud cover, precipitation where reported, observation time, data "
                "source and whether the data is live, cached or simulated.",
                CurrentWeatherInput,
                _get_current_weather,
            ),
            Tool(
                "get_weather_forecast",
                "Get a validated forecast for coordinates, as 3-hourly periods and daily summaries: "
                "temperature, rainfall amount in mm, rain probability in percent, humidity and wind. "
                "Rain probability and rainfall amount are separate facts.",
                ForecastInput,
                _get_weather_forecast,
            ),
            Tool(
                "get_crop_information",
                "Get crop requirements, growth stage information, irrigation considerations, weather "
                "sensitivities and source references. Also says whether rules exist for the crop. "
                "Give sowing_date to get PAU's irrigation timetable for wheat.",
                CropInformationInput,
                _get_crop_information,
            ),
            Tool(
                "assess_irrigation_need",
                "Run the irrigation decision engine. It retrieves and validates the weather itself "
                "from the coordinates, so you do not supply weather values. Returns an assessment, "
                "supporting factors, missing information, confidence and a suggested next action. "
                "Pass soil_moisture only if the farmer stated it.",
                IrrigationNeedInput,
                _assess_irrigation_need,
            ),
            Tool(
                "assess_weather_pest_risk",
                "Assess weather-related pest and disease risk. It retrieves and validates the weather "
                "itself from the coordinates. Returns potential risks, favourable conditions, a risk "
                "classification, evidence and monitoring actions. This shows favourable conditions "
                "only and cannot establish that a pest or disease is present.",
                PestRiskInput,
                _assess_weather_pest_risk,
            ),
            Tool(
                "get_location_information",
                "Resolve a place name or coordinates to coordinates, a resolved name, state, country "
                "and timezone offset where available.",
                LocationInput,
                _get_location_information,
            ),
            Tool(
                "save_recommendation",
                "Save a recommendation to the farmer's history. Call this only when the farmer has "
                "asked, in their latest message, to save or record it.",
                SaveRecommendationInput,
                _save_recommendation,
            ),
        ]
    )
