"""Alembic environment: async engine, URL taken from application settings."""

import asyncio
from logging.config import fileConfig

from alembic import context

from app.core.config import Settings
from app.database.base import UTCDateTime
from app.database.session import build_engine
from app.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _render_item(type_: str, obj, autogen_context):
    if type_ == "type" and isinstance(obj, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run_migrations_offline() -> None:
    context.configure(
        url=Settings().database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_item=_render_item,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, render_item=_render_item
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_online() -> None:
    engine = build_engine(Settings().database_url)
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_online())
