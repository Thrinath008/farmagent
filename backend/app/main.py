"""FastAPI application factory."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import anthropic
import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.farm_agent import FarmAgent
from app.api import agent, assessments, records, system, weather
from app.api.system import APP_VERSION
from app.core.config import Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.middleware import RateLimitMiddleware, RequestContextMiddleware, SafeErrorMiddleware
from app.database.session import build_engine, build_session_factory
from app.services.openweather import OpenWeatherClient
from app.services.weather import WeatherService
from app.tools.registry import build_registry


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx logs full request URLs at INFO, and OpenWeatherMap's API key travels in the query string.
    # The Anthropic SDK uses httpx2, which logs the same way.
    for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(name).setLevel(logging.WARNING)


def _build_anthropic_client(settings: Settings) -> anthropic.AsyncAnthropic | None:
    if not settings.ai_configured:
        return None
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        base_url=settings.anthropic_base_url,
        timeout=settings.anthropic_timeout_seconds,
        max_retries=settings.anthropic_max_retries,
    )


def create_app(
    settings: Settings | None = None,
    *,
    anthropic_client: Any | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    _configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = build_engine(settings.database_url)
        http = http_client or httpx.AsyncClient()
        model_client = anthropic_client or _build_anthropic_client(settings)

        app.state.settings = settings
        app.state.engine = engine
        app.state.session_factory = build_session_factory(engine)
        app.state.weather = WeatherService(
            OpenWeatherClient(http, settings), app.state.session_factory, settings
        )
        app.state.agent = FarmAgent(model_client, settings, build_registry())
        try:
            yield
        finally:
            if http_client is None:
                await http.aclose()
            if model_client is not None and anthropic_client is None:
                await model_client.close()
            await engine.dispose()

    app = FastAPI(
        title="FarmAgent API",
        version=APP_VERSION,
        description="Weather-aware farming decision support. Secrets stay on this backend.",
        lifespan=lifespan,
    )

    register_error_handlers(app)

    # The last added runs first, so CORS headers also reach rate-limited and error responses.
    app.add_middleware(SafeErrorMiddleware)
    app.add_middleware(RateLimitMiddleware, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Guest-Token"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestContextMiddleware)

    api = APIRouter(prefix="/api")
    api.include_router(system.router)
    api.include_router(weather.router)
    api.include_router(assessments.router)
    api.include_router(agent.router)
    api.include_router(records.router)
    app.include_router(api)
    return app


app = create_app()
