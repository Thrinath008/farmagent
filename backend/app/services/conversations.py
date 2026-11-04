"""Server-side conversation storage and the history sent to the model."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import NotFoundError
from app.intelligence.types import FarmingAdvice
from app.models import Conversation, Message, Recommendation

_TITLE_CHARS = 80


def title_from_message(message: str) -> str:
    line = " ".join(message.split())
    return line if len(line) <= _TITLE_CHARS else line[: _TITLE_CHARS - 1].rstrip() + "…"


async def list_conversations(session: AsyncSession, user_id: uuid.UUID) -> list[Conversation]:
    statement = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    return list(await session.scalars(statement))


async def get_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID, *, with_messages=False
) -> Conversation:
    statement = select(Conversation).where(
        Conversation.id == conversation_id, Conversation.user_id == user_id
    )
    if with_messages:
        statement = statement.options(selectinload(Conversation.messages))
    conversation = await session.scalar(statement)
    if conversation is None:
        raise NotFoundError("That conversation does not exist.")
    return conversation


async def create_conversation(
    session: AsyncSession, user_id: uuid.UUID, title: str, farm_id: uuid.UUID | None
) -> Conversation:
    conversation = Conversation(user_id=user_id, title=title, farm_id=farm_id)
    session.add(conversation)
    await session.flush()
    return conversation


async def delete_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> None:
    result = await session.execute(
        delete(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == user_id
        )
    )
    if result.rowcount == 0:
        raise NotFoundError("That conversation does not exist.")


async def load_history(session: AsyncSession, conversation_id: uuid.UUID, limit: int) -> list[dict]:
    """The latest messages as plain text. Earlier tool results are not replayed: weather goes stale,
    so the model must fetch it again rather than reuse what an earlier turn saw."""
    if limit <= 0:
        return []
    statement = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    rows = list(await session.scalars(statement))
    rows.reverse()
    history = [{"role": row.role, "content": row.content} for row in rows]
    while history and history[0]["role"] != "user":
        history.pop(0)
    return history


def assistant_text(advice: FarmingAdvice) -> str:
    return (
        f"{advice.recommendation}\n\n{advice.summary}" if advice.recommendation else advice.summary
    )


async def persist_exchange(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
    farm_id: uuid.UUID | None,
    user_message: str,
    advice: FarmingAdvice,
    tool_log: list[dict],
    saved_recommendation_ids: list[str],
) -> tuple[Conversation, Message]:
    """Store a finished exchange. Failed runs store nothing, so retrying cannot duplicate a message."""
    if conversation_id is None:
        conversation = await create_conversation(
            session, user_id, title_from_message(user_message), farm_id
        )
    else:
        conversation = await get_conversation(session, user_id, conversation_id)

    now = datetime.now(UTC)
    conversation.updated_at = now
    session.add(
        Message(conversation_id=conversation.id, role="user", content=user_message, created_at=now)
    )
    reply = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=assistant_text(advice),
        advice=advice.model_dump(mode="json"),
        tool_log=tool_log,
        created_at=datetime.now(UTC),
    )
    session.add(reply)

    # A recommendation saved during a brand-new conversation had no conversation row to point at yet.
    for saved_id in saved_recommendation_ids:
        record = await session.get(Recommendation, uuid.UUID(saved_id))
        if record is not None and record.user_id == user_id:
            record.conversation_id = conversation.id

    await session.flush()
    return conversation, reply
