"""FastAPI dependencies: settings, database sessions, guest identity, and shared services."""

import hashlib
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.farm_agent import FarmAgent
from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.database.session import SessionFactory
from app.models import User
from app.services.weather import WeatherService


def hash_guest_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_guest_token() -> str:
    return secrets.token_urlsafe(32)


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_session_factory(request: Request) -> SessionFactory:
    return request.app.state.session_factory


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


def get_weather(request: Request) -> WeatherService:
    return request.app.state.weather


def get_agent(request: Request) -> FarmAgent:
    return request.app.state.agent


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    x_guest_token: Annotated[str | None, Header(max_length=128)] = None,
) -> User:
    if not x_guest_token:
        raise UnauthorizedError()
    user = await session.scalar(
        select(User).where(User.guest_token_hash == hash_guest_token(x_guest_token))
    )
    if user is None:
        raise UnauthorizedError()
    return user


SessionDep = Annotated[AsyncSession, Depends(get_session)]
CurrentUser = Annotated[User, Depends(get_current_user)]
WeatherDep = Annotated[WeatherService, Depends(get_weather)]
AgentDep = Annotated[FarmAgent, Depends(get_agent)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]
