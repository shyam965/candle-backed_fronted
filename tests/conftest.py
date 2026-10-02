"""Test fixtures: a fresh MongoDB database per test, the real app lifespan, and an HTTPS client."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app

TEST_MONGO_URI = os.environ.get("TEST_MONGO_URI", "mongodb://localhost:27017")
BASE_URL = "https://testserver"


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        app_base_url=BASE_URL,
        mongo_uri=TEST_MONGO_URI,
        mongo_db_name=f"akrf_test_{uuid.uuid4().hex[:12]}",
        secret_key="t" * 48,
        cookie_secure=True,
        cors_origins="https://spa.example",
        upload_dir=tmp_path / "uploads",
        log_level="WARNING",
        mongo_timeout_ms=20000,
    )


@pytest.fixture
async def app(settings: Settings):
    application = create_app(settings)
    async with LifespanManager(application):
        try:
            yield application
        finally:
            await application.state.mongo_client.drop_database(settings.database_name)


@pytest.fixture
async def client(app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as c:
        yield c


@pytest.fixture
def db(app):
    return app.state.db
