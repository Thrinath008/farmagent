"""Saved recommendations, always scoped to their owner."""

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.intelligence.types import FarmingAdvice
from app.models import Recommendation


async def save_advice(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    advice: FarmingAdvice,
    origin: str,
    farm_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    crop: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> Recommendation:
    weather = advice.weather_context
    record = Recommendation(
        user_id=user_id,
        farm_id=farm_id,
        conversation_id=conversation_id,
        origin=origin,
        intent=advice.intent.value,
        crop=crop,
        recommendation=advice.recommendation,
        summary=advice.summary,
        risk_level=advice.risk_level.value,
        confidence=advice.confidence.value,
        advice=advice.model_dump(mode="json"),
        weather_provenance=weather.provenance.value if weather else None,
        weather_observed_at=weather.observed_at if weather else None,
        latitude=latitude,
        longitude=longitude,
    )
    session.add(record)
    await session.flush()
    return record


async def list_recommendations(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    limit: int = 50,
    farm_id: uuid.UUID | None = None,
    intent: str | None = None,
) -> list[Recommendation]:
    statement = (
        select(Recommendation)
        .where(Recommendation.user_id == user_id)
        .order_by(Recommendation.created_at.desc())
        .limit(limit)
    )
    if farm_id is not None:
        statement = statement.where(Recommendation.farm_id == farm_id)
    if intent is not None:
        statement = statement.where(Recommendation.intent == intent)
    return list(await session.scalars(statement))


async def delete_recommendation(
    session: AsyncSession, user_id: uuid.UUID, recommendation_id: uuid.UUID
) -> None:
    result = await session.execute(
        delete(Recommendation).where(
            Recommendation.id == recommendation_id, Recommendation.user_id == user_id
        )
    )
    if result.rowcount == 0:
        raise NotFoundError("That recommendation does not exist.")
