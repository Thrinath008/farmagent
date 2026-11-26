"""Async engine and session management."""

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

SessionFactory = async_sessionmaker[AsyncSession]


def build_engine(database_url: str) -> AsyncEngine:
    if database_url.startswith("sqlite"):
        engine = create_async_engine(database_url)

        @event.listens_for(engine.sync_engine, "connect")
        def _enforce_foreign_keys(connection, _record) -> None:
            connection.execute("PRAGMA foreign_keys=ON")

        return engine
    return create_async_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        # Neon's pooled connections go through PgBouncer in transaction mode, so the app does not
        # rely on server-side prepared statements.
        connect_args={"prepare_threshold": None},
    )


def build_session_factory(engine: AsyncEngine) -> SessionFactory:
    return async_sessionmaker(engine, expire_on_commit=False)
