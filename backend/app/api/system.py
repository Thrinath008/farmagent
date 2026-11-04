"""Health, guest sessions and the crop catalogue."""

import logging

from fastapi import APIRouter, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import (
    CurrentUser,
    SessionDep,
    SessionFactoryDep,
    SettingsDep,
    hash_guest_token,
    new_guest_token,
)
from app.intelligence.crops import CROPS
from app.intelligence.sources import resolve
from app.intelligence.types import IrrigationMethod, SoilMoisture, SoilType
from app.models import User
from app.schemas.api import (
    CatalogResponse,
    CropRead,
    GuestSessionResponse,
    HealthResponse,
    StageRead,
    UserRead,
    UserUpdate,
)

logger = logging.getLogger("farmagent.system")
router = APIRouter()

APP_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health(settings: SettingsDep, factory: SessionFactoryDep) -> HealthResponse:
    database = "ok"
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("health check database failure type=%s", type(exc).__name__)
        database = "unavailable"
    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=APP_VERSION,
        environment=settings.environment,
        database=database,
        weather_configured=settings.weather_configured,
        ai_configured=settings.ai_configured,
        ai_model=settings.anthropic_model if settings.ai_configured else None,
    )


@router.post(
    "/session/guest",
    response_model=GuestSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["session"],
)
async def create_guest_session(session: SessionDep) -> GuestSessionResponse:
    token = new_guest_token()
    user = User(guest_token_hash=hash_guest_token(token))
    session.add(user)
    await session.commit()
    return GuestSessionResponse(token=token, user=UserRead.model_validate(user))


@router.get("/session/me", response_model=UserRead, tags=["session"])
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/session/me", response_model=UserRead, tags=["session"])
async def update_me(data: UserUpdate, user: CurrentUser, session: SessionDep) -> User:
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "preferred_language" and value is None:
            continue
        setattr(user, key, value)
    await session.commit()
    return user


@router.delete("/session/me", status_code=status.HTTP_204_NO_CONTENT, tags=["session"])
async def delete_me(user: CurrentUser, session: SessionDep) -> Response:
    """Delete this guest and every farm, conversation and recommendation they own."""
    await session.delete(user)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/crops", response_model=CatalogResponse, tags=["crops"])
async def crop_catalog() -> CatalogResponse:
    return CatalogResponse(
        crops=[
            CropRead(
                id=profile.id,
                name=profile.name,
                support_level=profile.support,
                support_note=profile.support_note,
                stages=[
                    StageRead(
                        id=s.id,
                        label=s.label,
                        irrigation_critical=s.irrigation_critical,
                        note=s.note,
                    )
                    for s in profile.stages
                ],
                irrigation_considerations=list(profile.irrigation_considerations),
                sources=resolve(profile.source_ids),
            )
            for profile in CROPS.values()
        ],
        soil_types=[s.value for s in SoilType if s != SoilType.UNKNOWN],
        irrigation_methods=[m.value for m in IrrigationMethod if m != IrrigationMethod.UNKNOWN],
        soil_moisture_levels=[m.value for m in SoilMoisture],
        area_units=["acre", "hectare", "kanal", "bigha"],
    )
