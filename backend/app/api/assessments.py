"""Irrigation and pest-risk endpoints: the decision engine directly, with no AI involved."""

from dataclasses import dataclass

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep, WeatherDep
from app.intelligence.irrigation import IrrigationInput, assess_irrigation
from app.intelligence.pest_risk import assess_pest_risk
from app.intelligence.recommendation import advice_from_irrigation, advice_from_pest_risk
from app.intelligence.types import IrrigationMethod, SoilType
from app.models import Farm, FarmCrop
from app.schemas.api import (
    ApiIssue,
    AssessmentTarget,
    IrrigationRequest,
    IrrigationResponse,
    PestRiskRequest,
    PestRiskResponse,
)
from app.services import farms as farm_service
from app.services.assessments import WeatherBundle, load_weather

router = APIRouter(tags=["assessments"])

_NO_LOCATION = ApiIssue(
    code="location_missing",
    message="No location is set. Add coordinates to this farm, or choose a location.",
)


@dataclass
class _Resolved:
    farm: Farm | None
    crop_record: FarmCrop | None
    crop: str
    growth_stage: str | None
    latitude: float | None
    longitude: float | None


async def _resolve(target: AssessmentTarget, user_id, session) -> _Resolved:
    farm = crop_record = None
    if target.farm_id is not None:
        farm = await farm_service.get_farm(session, user_id, target.farm_id)
        if target.farm_crop_id is not None:
            crop_record = farm_service.find_crop(farm, target.farm_crop_id)
    latitude = target.latitude if target.latitude is not None else (farm.latitude if farm else None)
    longitude = (
        target.longitude if target.longitude is not None else (farm.longitude if farm else None)
    )
    # The weather request may take a while. Give the database connection back to the pool first.
    await session.commit()
    return _Resolved(
        farm=farm,
        crop_record=crop_record,
        crop=target.crop or (crop_record.crop if crop_record else "wheat"),
        growth_stage=target.growth_stage or (crop_record.growth_stage if crop_record else None),
        latitude=latitude,
        longitude=longitude,
    )


async def _weather_for(resolved: _Resolved, provider, force_refresh: bool) -> WeatherBundle:
    if resolved.latitude is None or resolved.longitude is None:
        return WeatherBundle()
    return await load_weather(
        provider, resolved.latitude, resolved.longitude, force_refresh=force_refresh
    )


def _issues(resolved: _Resolved, bundle: WeatherBundle) -> list[ApiIssue]:
    if resolved.latitude is None or resolved.longitude is None:
        return [_NO_LOCATION]
    return [ApiIssue(code=e.code, message=e.message) for e in bundle.errors]


@router.post("/irrigation/assess", response_model=IrrigationResponse)
async def assess_irrigation_endpoint(
    data: IrrigationRequest, user: CurrentUser, session: SessionDep, weather: WeatherDep
) -> IrrigationResponse:
    resolved = await _resolve(data, user.id, session)
    bundle = await _weather_for(resolved, weather, data.force_refresh)
    snapshot = bundle.snapshot

    soil = data.soil_type
    if soil is None and resolved.farm is not None and resolved.farm.soil_type:
        soil = SoilType(resolved.farm.soil_type)
    method = data.irrigation_method
    if (
        method is None
        and resolved.crop_record is not None
        and resolved.crop_record.irrigation_method
    ):
        method = IrrigationMethod(resolved.crop_record.irrigation_method)
    sowing = data.sowing_date or (
        resolved.crop_record.sowing_date if resolved.crop_record else None
    )

    assessment = assess_irrigation(
        IrrigationInput(
            crop=resolved.crop,
            growth_stage=resolved.growth_stage,
            soil_type=soil or SoilType.UNKNOWN,
            soil_moisture=data.soil_moisture,
            irrigation_method=method or IrrigationMethod.UNKNOWN,
            recent_rainfall_mm=data.recent_rainfall_mm,
            sowing_date=sowing,
        ),
        snapshot,
    )
    return IrrigationResponse(
        assessment=assessment,
        advice=advice_from_irrigation(assessment, snapshot),
        weather=snapshot,
        weather_issues=_issues(resolved, bundle),
        farm_id=resolved.farm.id if resolved.farm else None,
    )


@router.post("/pest-risk/assess", response_model=PestRiskResponse)
async def assess_pest_risk_endpoint(
    data: PestRiskRequest, user: CurrentUser, session: SessionDep, weather: WeatherDep
) -> PestRiskResponse:
    resolved = await _resolve(data, user.id, session)
    bundle = await _weather_for(resolved, weather, data.force_refresh)
    snapshot = bundle.snapshot
    assessment = assess_pest_risk(resolved.crop, resolved.growth_stage, snapshot)
    return PestRiskResponse(
        assessment=assessment,
        advice=advice_from_pest_risk(assessment, snapshot),
        weather=snapshot,
        weather_issues=_issues(resolved, bundle),
        farm_id=resolved.farm.id if resolved.farm else None,
    )
