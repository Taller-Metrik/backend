"""Fixtures compartidas.

Por defecto las pruebas usan SQLite en memoria. Para correr la integración contra
PostgreSQL real:  set TEST_DATABASE_URL=postgresql+asyncpg://usuario:clave@localhost/metrik_test
"""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401
from app.core.database import Base, get_db
from app.main import create_app

pytest_plugins = ["tests.evidencia_plugin"]

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
API = "/api/v1"


def _make_engine():
    if TEST_DATABASE_URL.startswith("sqlite"):
        return create_async_engine(
            TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
    return create_async_engine(TEST_DATABASE_URL)


@pytest_asyncio.fixture
async def db_engine():
    engine = _make_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncGenerator[AsyncClient, None]:
    application = create_app(use_lifespan=False)
    session_factory = async_sessionmaker(db_engine, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as ac:
        yield ac


USUARIO = {"email": "ana@metrik.pe", "full_name": "Ana Medidora", "password": "clave-segura-123"}


@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    resp = await client.post(f"{API}/auth/register", json=USUARIO)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, registered_user: dict) -> AsyncClient:
    resp = await client.post(
        f"{API}/auth/login", data={"username": USUARIO["email"], "password": USUARIO["password"]}
    )
    assert resp.status_code == 200, resp.text
    client.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
    return client


@pytest.fixture
def api() -> str:
    return API
