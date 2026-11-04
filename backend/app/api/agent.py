"""Agent endpoints. Chat is offered whole or as a stream of agent events.

The stream carries agent progress (each tool as it starts and finishes) and then the finished answer.
Answer text is not streamed token by token, because an answer may only reach the farmer after it has
passed backend validation.
"""

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agents.farm_agent import AgentResult
from app.agents.prompts import build_context_block
from app.api.deps import (
    AgentDep,
    CurrentUser,
    SessionDep,
    SessionFactoryDep,
    SettingsDep,
    WeatherDep,
)
from app.core.config import Settings
from app.core.errors import AgentNotConfiguredError, AppError, BadRequestError
from app.database.session import SessionFactory
from app.models import User
from app.schemas.api import (
    AnalyzeRequest,
    AnalyzeResponse,
    ChatRequest,
    ChatResponse,
    ToolLogEntry,
)
from app.services import conversations as conversation_service
from app.services import farms as farm_service
from app.tools.base import ToolContext

logger = logging.getLogger("farmagent.agent")
router = APIRouter(prefix="/agent", tags=["agent"])

# An explicit request in this message is what unlocks the save_recommendation tool.
_SAVE_REQUEST = re.compile(
    r"\b(save|saved|saving|record|log|store|bookmark|keep a note|note this|note that|remember this)\b"
    r"|सेव|सहेज|ਸੇਵ|సేవ్",
    re.IGNORECASE,
)


def message_requests_save(message: str) -> bool:
    return _SAVE_REQUEST.search(message) is not None


def _farmer_context(user: User) -> dict:
    return {"display_name": user.display_name, "preferred_language": user.preferred_language}


def _check_length(message: str, settings: Settings) -> None:
    if len(message) > settings.agent_max_message_chars:
        raise BadRequestError(
            f"That message is too long. Keep it under {settings.agent_max_message_chars} characters."
        )


async def _prepare(
    data: ChatRequest, user: User, session, settings: Settings, weather, factory: SessionFactory
) -> tuple[dict, list[dict]]:
    """Check ownership and build everything the run needs, before any streaming begins."""
    _check_length(data.message, settings)
    farm_id = data.farm_id
    history: list[dict] = []
    if data.conversation_id is not None:
        conversation = await conversation_service.get_conversation(
            session, user.id, data.conversation_id
        )
        farm_id = farm_id or conversation.farm_id
        history = await conversation_service.load_history(
            session, data.conversation_id, settings.agent_history_messages
        )
    farm = await farm_service.get_farm(session, user.id, farm_id) if farm_id else None
    context_block = build_context_block(_farmer_context(user), farm_service.farm_context(farm))
    context = ToolContext(
        weather=weather,
        session_factory=factory,
        user_id=user.id,
        farm_id=farm.id if farm else None,
        conversation_id=data.conversation_id,
        allow_save=message_requests_save(data.message),
    )
    # The agent can run for minutes. Give the database connection back to the pool first.
    await session.commit()
    return {"context_block": context_block, "context": context, "farm_id": farm_id}, history


async def _persist(
    factory: SessionFactory, data: ChatRequest, user_id, prep: dict, result: AgentResult
):
    async with factory() as session:
        conversation, reply = await conversation_service.persist_exchange(
            session,
            user_id=user_id,
            conversation_id=data.conversation_id,
            farm_id=prep["farm_id"],
            user_message=data.message,
            advice=result.advice,
            tool_log=result.tool_log,
            saved_recommendation_ids=prep["context"].saved_recommendation_ids,
        )
        await session.commit()
    return ChatResponse(
        conversation_id=conversation.id,
        message_id=reply.id,
        advice=result.advice,
        tool_log=[ToolLogEntry(**entry) for entry in result.tool_log],
        saved_recommendation_ids=prep["context"].saved_recommendation_ids,
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    data: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    agent: AgentDep,
    settings: SettingsDep,
    weather: WeatherDep,
    factory: SessionFactoryDep,
) -> ChatResponse:
    prep, history = await _prepare(data, user, session, settings, weather, factory)
    result = await agent.run(
        user_message=data.message,
        context_block=prep["context_block"],
        context=prep["context"],
        history=history,
    )
    return await _persist(factory, data, user.id, prep, result)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/chat/stream")
async def chat_stream(
    data: ChatRequest,
    user: CurrentUser,
    session: SessionDep,
    agent: AgentDep,
    settings: SettingsDep,
    weather: WeatherDep,
    factory: SessionFactoryDep,
) -> StreamingResponse:
    if agent.is_unconfigured:
        raise AgentNotConfiguredError()
    prep, history = await _prepare(data, user, session, settings, weather, factory)
    user_id = user.id

    async def events() -> AsyncIterator[str]:
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def work() -> None:
            try:
                result = await agent.run(
                    user_message=data.message,
                    context_block=prep["context_block"],
                    context=prep["context"],
                    history=history,
                    emit=queue.put,
                )
                response = await _persist(factory, data, user_id, prep, result)
                await queue.put({"type": "final", "response": response.model_dump(mode="json")})
            except AppError as exc:
                await queue.put({"type": "error", "code": exc.code, "message": exc.message})
            except Exception:
                logger.exception("agent stream failed")
                await queue.put(
                    {"type": "error", "code": "internal_error", "message": AppError.message}
                )
            finally:
                await queue.put(None)

        task = asyncio.create_task(work())
        try:
            while (event := await queue.get()) is not None:
                yield _sse(event)
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    data: AnalyzeRequest,
    user: CurrentUser,
    session: SessionDep,
    agent: AgentDep,
    weather: WeatherDep,
) -> AnalyzeResponse:
    """A one-off farm briefing for the dashboard. Nothing is saved."""
    farm = await farm_service.get_farm(session, user.id, data.farm_id)
    crop_note = ""
    if data.farm_crop_id is not None:
        crop = farm_service.find_crop(farm, data.farm_crop_id)
        crop_note = f" Focus on my {crop.crop}."
    focus = f" I am especially interested in: {data.focus}" if data.focus else ""
    question = (
        "Give me today's briefing for this farm: what the weather means for my crops, whether "
        f"irrigation looks necessary, and what to watch this week.{crop_note}{focus}"
    )
    context = ToolContext(
        weather=weather, user_id=user.id, farm_id=farm.id, allow_save=False, origin="assistant"
    )
    context_block = build_context_block(_farmer_context(user), farm_service.farm_context(farm))
    await session.commit()
    result = await agent.run(user_message=question, context_block=context_block, context=context)
    return AnalyzeResponse(
        advice=result.advice, tool_log=[ToolLogEntry(**entry) for entry in result.tool_log]
    )
