"""Farms, conversations, saved recommendations and the Scenario Lab."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import AgentDep, CurrentUser, SessionDep
from app.schemas.api import (
    ConversationCreate,
    ConversationDetail,
    ConversationRead,
    FarmCreate,
    FarmCropCreate,
    FarmCropRead,
    FarmCropUpdate,
    FarmRead,
    FarmUpdate,
    RecommendationCreate,
    RecommendationRead,
    ScenarioDefinition,
    ScenarioRunRequest,
    ScenarioRunResponse,
)
from app.services import conversations as conversation_service
from app.services import farms as farm_service
from app.services import recommendations as recommendation_service
from app.services.scenarios import SCENARIOS, run_scenarios

router = APIRouter()


def _no_content() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# Farms


@router.get("/farms", response_model=list[FarmRead], tags=["farms"])
async def list_farms(user: CurrentUser, session: SessionDep) -> list[FarmRead]:
    farms = await farm_service.list_farms(session, user.id)
    return [farm_service.farm_to_read(farm) for farm in farms]


@router.post("/farms", response_model=FarmRead, status_code=status.HTTP_201_CREATED, tags=["farms"])
async def create_farm(data: FarmCreate, user: CurrentUser, session: SessionDep) -> FarmRead:
    farm = await farm_service.create_farm(session, user.id, data)
    await session.commit()
    farm = await farm_service.get_farm(session, user.id, farm.id)
    return farm_service.farm_to_read(farm)


@router.get("/farms/{farm_id}", response_model=FarmRead, tags=["farms"])
async def read_farm(farm_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> FarmRead:
    return farm_service.farm_to_read(await farm_service.get_farm(session, user.id, farm_id))


@router.patch("/farms/{farm_id}", response_model=FarmRead, tags=["farms"])
async def update_farm(
    farm_id: uuid.UUID, data: FarmUpdate, user: CurrentUser, session: SessionDep
) -> FarmRead:
    farm = await farm_service.get_farm(session, user.id, farm_id)
    await farm_service.update_farm(session, farm, data)
    await session.commit()
    return farm_service.farm_to_read(farm)


@router.delete("/farms/{farm_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["farms"])
async def delete_farm(farm_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    farm = await farm_service.get_farm(session, user.id, farm_id)
    await session.delete(farm)
    await session.commit()
    return _no_content()


@router.post(
    "/farms/{farm_id}/crops",
    response_model=FarmCropRead,
    status_code=status.HTTP_201_CREATED,
    tags=["farms"],
)
async def add_crop(
    farm_id: uuid.UUID, data: FarmCropCreate, user: CurrentUser, session: SessionDep
) -> FarmCropRead:
    farm = await farm_service.get_farm(session, user.id, farm_id)
    crop = await farm_service.add_crop(session, farm, data)
    await session.commit()
    return farm_service.crop_to_read(crop)


@router.patch("/farms/{farm_id}/crops/{crop_id}", response_model=FarmCropRead, tags=["farms"])
async def update_crop(
    farm_id: uuid.UUID,
    crop_id: uuid.UUID,
    data: FarmCropUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> FarmCropRead:
    farm = await farm_service.get_farm(session, user.id, farm_id)
    crop = farm_service.find_crop(farm, crop_id)
    await farm_service.update_crop(session, crop, data)
    await session.commit()
    return farm_service.crop_to_read(crop)


@router.delete(
    "/farms/{farm_id}/crops/{crop_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["farms"]
)
async def delete_crop(
    farm_id: uuid.UUID, crop_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    farm = await farm_service.get_farm(session, user.id, farm_id)
    await session.delete(farm_service.find_crop(farm, crop_id))
    await session.commit()
    return _no_content()


# Conversations


@router.get("/conversations", response_model=list[ConversationRead], tags=["conversations"])
async def list_conversations(user: CurrentUser, session: SessionDep):
    return await conversation_service.list_conversations(session, user.id)


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["conversations"],
)
async def create_conversation(data: ConversationCreate, user: CurrentUser, session: SessionDep):
    if data.farm_id is not None:
        await farm_service.get_farm(session, user.id, data.farm_id)
    conversation = await conversation_service.create_conversation(
        session, user.id, data.title or "New conversation", data.farm_id
    )
    await session.commit()
    return conversation


@router.get(
    "/conversations/{conversation_id}", response_model=ConversationDetail, tags=["conversations"]
)
async def read_conversation(conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep):
    return await conversation_service.get_conversation(
        session, user.id, conversation_id, with_messages=True
    )


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["conversations"],
)
async def delete_conversation(
    conversation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await conversation_service.delete_conversation(session, user.id, conversation_id)
    await session.commit()
    return _no_content()


# Recommendations


@router.get("/recommendations", response_model=list[RecommendationRead], tags=["recommendations"])
async def list_recommendations(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    farm_id: uuid.UUID | None = None,
    intent: Annotated[str | None, Query(max_length=40)] = None,
):
    return await recommendation_service.list_recommendations(
        session, user.id, limit=limit, farm_id=farm_id, intent=intent
    )


@router.post(
    "/recommendations",
    response_model=RecommendationRead,
    status_code=status.HTTP_201_CREATED,
    tags=["recommendations"],
)
async def create_recommendation(data: RecommendationCreate, user: CurrentUser, session: SessionDep):
    """Save a result the farmer chose to keep."""
    if data.farm_id is not None:
        await farm_service.get_farm(session, user.id, data.farm_id)
    if data.conversation_id is not None:
        await conversation_service.get_conversation(session, user.id, data.conversation_id)
    record = await recommendation_service.save_advice(
        session,
        user_id=user.id,
        advice=data.advice,
        origin=data.origin,
        farm_id=data.farm_id,
        conversation_id=data.conversation_id,
        crop=data.crop,
        latitude=data.latitude,
        longitude=data.longitude,
    )
    await session.commit()
    return record


@router.delete(
    "/recommendations/{recommendation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["recommendations"],
)
async def delete_recommendation(
    recommendation_id: uuid.UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await recommendation_service.delete_recommendation(session, user.id, recommendation_id)
    await session.commit()
    return _no_content()


# Scenario Lab


@router.get("/scenarios", response_model=list[ScenarioDefinition], tags=["scenarios"])
async def list_scenarios() -> list[ScenarioDefinition]:
    return list(SCENARIOS.values())


@router.post("/scenarios/run", response_model=ScenarioRunResponse, tags=["scenarios"])
async def run_scenarios_endpoint(data: ScenarioRunRequest, agent: AgentDep) -> ScenarioRunResponse:
    return await run_scenarios(data.scenario_ids, agent, include_ai=data.include_ai)
