from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings
from app.db import get_session
from app.main import app
from app.models import Base
from tests.helpers import reset_db


class TestEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    test_database_url: str | None = None


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    url = TestEnv().test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL не задан (см. .env.example)", returncode=1)
    if url == settings.database_url:
        pytest.exit("TEST_DATABASE_URL совпадает с DATABASE_URL: тесты удалят схему", returncode=1)

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def clean_db(engine: AsyncEngine, session_factory: async_sessionmaker[AsyncSession]) -> None:
    await reset_db(engine, session_factory)


@pytest.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> AsyncIterator[AsyncSession]:
    """Отдельная сессия для проверки состояния БД из тестов."""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], clean_db: None
) -> AsyncIterator[AsyncClient]:
    # ASGITransport не запускает lifespan: seed делает clean_db, основная БД не трогается
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
