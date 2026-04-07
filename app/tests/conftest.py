import os

os.environ["REDIS_URL"] = "redis://localhost:6379/0"

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db

TEST_DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db"

async_engine = create_async_engine(TEST_DATABASE_URL)
TestSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def override_get_db():
    """Override get_db for tests - use test database sessions."""
    async with TestSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db

@pytest.fixture()
def client():
    """Get a test client"""
    with TestClient(app) as client:
        yield client