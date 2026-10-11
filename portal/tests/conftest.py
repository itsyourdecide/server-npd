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
from sqlalchemy import text

TRUNCATE_TABLES = (
    "operations",
    "virtual_machines",
    "ssh_public_keys",
    "user_quota",
    "compute_plans",
    "application_sessions",
    "external_identities",
    "users",
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