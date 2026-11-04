"""Farm and crop persistence, always scoped to the owning user."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import BadRequestError, NotFoundError
from app.intelligence.crops import get_crop
from app.intelligence.growth_stages import schedule_for_crop
from app.models import Farm, FarmCrop
from app.schemas.api import (
    FarmCreate,
    FarmCropCreate,
    FarmCropRead,
    FarmCropUpdate,
    FarmRead,
    FarmUpdate,
)


def _enum_value(value):
    return getattr(value, "value", value)


async def list_farms(session: AsyncSession, user_id: uuid.UUID) -> list[Farm]:
    statement = (
        select(Farm)
        .where(Farm.user_id == user_id)
        .options(selectinload(Farm.crops))
        .order_by(Farm.created_at)
    )
    return list(await session.scalars(statement))


async def get_farm(session: AsyncSession, user_id: uuid.UUID, farm_id: uuid.UUID) -> Farm:
    statement = (
        select(Farm)
        .where(Farm.id == farm_id, Farm.user_id == user_id)
        .options(selectinload(Farm.crops))
    )
    farm = await session.scalar(statement)
    if farm is None:
        raise NotFoundError("That farm does not exist.")
    return farm


async def create_farm(session: AsyncSession, user_id: uuid.UUID, data: FarmCreate) -> Farm:
    fields = data.model_dump(exclude={"crops"})
    fields["soil_type"] = _enum_value(fields["soil_type"])
    farm = Farm(user_id=user_id, **fields, crops=[_new_crop(crop) for crop in data.crops])
    session.add(farm)
    await session.flush()
    return farm


async def update_farm(session: AsyncSession, farm: Farm, data: FarmUpdate) -> Farm:
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(farm, key, _enum_value(value))
    farm.updated_at = datetime.now(UTC)
    await session.flush()
    return farm


def _new_crop(data: FarmCropCreate) -> FarmCrop:
    fields = data.model_dump()
    fields["irrigation_method"] = _enum_value(fields["irrigation_method"])
    return FarmCrop(**fields)


async def add_crop(session: AsyncSession, farm: Farm, data: FarmCropCreate) -> FarmCrop:
    crop = _new_crop(data)
    crop.farm_id = farm.id
    session.add(crop)
    await session.flush()
    return crop


def find_crop(farm: Farm, crop_id: uuid.UUID) -> FarmCrop:
    crop = next((c for c in farm.crops if c.id == crop_id), None)
    if crop is None:
        raise NotFoundError("That crop is not on this farm.")
    return crop


async def update_crop(session: AsyncSession, crop: FarmCrop, data: FarmCropUpdate) -> FarmCrop:
    updates = data.model_dump(exclude_unset=True)
    stage_id = updates.get("growth_stage")
    profile = get_crop(crop.crop)
    if stage_id and profile and profile.stages:
        stage = profile.stage(stage_id)
        if stage is None:
            raise BadRequestError(f"'{stage_id}' is not a growth stage of {profile.name}.")
        updates["growth_stage"] = stage.id
    for key, value in updates.items():
        setattr(crop, key, _enum_value(value))
    crop.updated_at = datetime.now(UTC)
    await session.flush()
    return crop


def crop_to_read(crop: FarmCrop) -> FarmCropRead:
    profile = get_crop(crop.crop)
    stage = profile.stage(crop.growth_stage) if profile else None
    read = FarmCropRead.model_validate(crop)
    read.crop_name = profile.name if profile else crop.crop
    read.support_level = profile.support if profile else "planned"
    read.growth_stage_label = stage.label if stage else crop.growth_stage
    read.irrigation_schedule = schedule_for_crop(
        crop.crop, crop.sowing_date, datetime.now(UTC).date()
    )
    return read


def farm_to_read(farm: Farm) -> FarmRead:
    read = FarmRead.model_validate(farm, from_attributes=True)
    read.crops = [crop_to_read(crop) for crop in farm.crops]
    return read


def farm_context(farm: Farm | None) -> dict | None:
    """Farm details for the agent. Unset fields stay null so the model cannot read them as facts."""
    if farm is None:
        return None
    return {
        "id": str(farm.id),
        "name": farm.name,
        "location_name": farm.location_name,
        "state": farm.state,
        "country": farm.country,
        "latitude": farm.latitude,
        "longitude": farm.longitude,
        "size": farm.size_value,
        "area_unit": farm.area_unit,
        "soil_type": farm.soil_type,
        "crops": [
            {
                "crop": crop.crop,
                "variety": crop.variety,
                "sowing_date": crop.sowing_date.isoformat() if crop.sowing_date else None,
                "growth_stage": crop.growth_stage,
                "irrigation_method": crop.irrigation_method,
                "rule_support": (get_crop(crop.crop).support if get_crop(crop.crop) else "planned"),
            }
            for crop in farm.crops
        ],
    }
