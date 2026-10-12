import os

TEST_DATABASE_URL = "postgresql+psycopg://portal:portal@127.0.0.1:5433/portal_test"
ADMIN_DATABASE_URL = "postgresql://portal:portal@127.0.0.1:5433/portal"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL

import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from app.db.session import SessionLocal
from app.identity.services import get_or_create_user
from sqlalchemy import text

TRUNCATE_TABLES = (
    "operations",
    "virtual_machines",
    "ssh_public_keys",
    "user_quota",
    "application_sessions",
    "external_identities",
    "users",
    # compute_plans НЕ трогаем: план starter сеет миграция
    # 903299d0b202 — это базовые данные системы, а не тестовый мусор.
)

def _ensure_test_database() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = 'portal_test'"
        ).fetchone()
        if not exists:
            conn.execute("CREATE DATABASE portal_test")

def _migrate_to_head() -> None:
    command.upgrade(Config("alembic.ini"), "head")

@pytest.fixture(scope="session", autouse=True)
def test_database() -> None:
    _ensure_test_database()
    _migrate_to_head()

@pytest_asyncio.fixture
async def db():
    async with SessionLocal() as session:
        yield session
    async with SessionLocal() as session:
        await session.execute(text(
            "TRUNCATE TABLE " + ", ".join(TRUNCATE_TABLES)
            + " RESTART IDENTITY CASCADE"
        ))
        await session.commit()

@pytest_asyncio.fixture
async def user(db):
    # TODO: нужен отдельный тест для проверки функции get_or_create_user
    user = await get_or_create_user(
        db=db,
        issuer="issuer",
        subject="subject",
        email="email@example.com",
    )
    return user

@pytest_asyncio.fixture
async def client():
    # Приложение ходит в portal_test через собственные сессии get_db,
    # поэтому данные, которые должны быть ему видны, тесты обязаны коммитить.
    from app.main import create_app

    import httpx2

    app = create_app()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://testserver",
    ) as http_client:
        yield http_client