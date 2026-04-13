import asyncio
import os

import asyncpg
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_DB = "test_db"
_AUTH = "postgresql://postgres:postgres@localhost:5432/postgres"
_APP = f"postgresql://postgres:postgres@localhost:5432/{TEST_DB}"

os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["DATABASE_URL"] = _APP

from app.main import app
from app.database import engine, get_db

ASYNC_URL = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{TEST_DB}"


async def _ensure_db():
    conn = await asyncpg.connect(_AUTH)
    try:
        if await conn.fetchrow("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB) is None:
            await conn.execute(f"CREATE DATABASE {TEST_DB}")
    finally:
        await conn.close()


async def _drop_db():
    conn = await asyncpg.connect(_AUTH)
    try:
        await conn.execute(
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = $1 AND pid <> pg_backend_pid()",
            TEST_DB,
        )
        await conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    finally:
        await conn.close()


def pytest_configure(config):
    asyncio.run(_ensure_db())


def pytest_sessionfinish(session, exitstatus):
    async def cleanup():
        await engine.dispose()
        await async_engine.dispose()
        await _drop_db()

    try:
        asyncio.run(cleanup())
    except RuntimeError:
        pass


async_engine = create_async_engine(ASYNC_URL)
TestSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def override_get_db():
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as client:
        yield client
