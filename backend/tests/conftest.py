"""Fixtures. No test reaches a live external API: HTTP is mocked and the model is scripted.

Set TEST_DATABASE_URL to run the suite against PostgreSQL rather than the default SQLite file.
"""

import os
import socket

import httpx
import pytest
import pytest_asyncio
import respx

from app.core.config import Settings
from app.database.session import build_engine, build_session_factory
from app.main import create_app
from app.models import Base
from tests.factories import FakeAnthropic

OWM = "https://api.openweathermap.org"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@pytest.fixture(autouse=True)
def _no_external_network(monkeypatch):
    """Fail loudly if anything tries to reach a real host. Mocks have to be doing the work."""
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        if name not in _LOCAL_HOSTS:
            raise AssertionError(f"A test tried to reach the network: {name}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)


@pytest.fixture
def database_url(tmp_path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite+aiosqlite:///{tmp_path}/test.db"


@pytest.fixture
def make_settings(database_url):
    def _make(**overrides) -> Settings:
        values = {
            "environment": "test",
            "database_url": database_url,
            "openweather_api_key": "owm-test-secret",
            "anthropic_api_key": "anthropic-test-secret",
            "anthropic_model": "claude-test-model",
            "rate_limit_enabled": False,
            "openweather_retry_backoff_seconds": 0.0,
            "frontend_url": "https://farmagent.example",
        }
        values.update(overrides)
        return Settings(_env_file=None, **values)

    return _make


@pytest.fixture
def settings(make_settings) -> Settings:
    return make_settings()


@pytest_asyncio.fixture
async def session_factory(database_url):
    engine = build_engine(database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    yield build_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def owm():
    with respx.mock(base_url=OWM, assert_all_called=False) as router:
        yield router


@pytest.fixture
def fake_model() -> FakeAnthropic:
    return FakeAnthropic()


@pytest_asyncio.fixture
async def make_client(session_factory, settings, fake_model):
    """Builds an API client for a configured app. session_factory has already created the tables."""
    started = []

    async def _make(app_settings=None, model=fake_model, raise_app_exceptions=True):
        app = create_app(app_settings or settings, anthropic_client=model)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=raise_app_exceptions)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver")
        started.append((client, lifespan))
        return client

    yield _make
    for client, lifespan in started:
        await client.aclose()
        await lifespan.__aexit__(None, None, None)


@pytest_asyncio.fixture
async def client(make_client):
    return await make_client()


@pytest_asyncio.fixture
async def guest(client) -> dict:
    """Headers for a fresh guest session."""
    response = await client.post("/api/session/guest")
    assert response.status_code == 201
    return {"X-Guest-Token": response.json()["token"]}
