"""PostgreSQL integration test infrastructure."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import Database


@pytest.fixture(scope="session")
def migrated_database_url() -> Iterator[str]:
    """Apply the complete migration chain to an explicitly isolated test DB."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("TEST_DATABASE_URL is not configured")

    parsed_url = make_url(database_url)
    if parsed_url.drivername != "postgresql+asyncpg":
        raise RuntimeError("Integration tests require PostgreSQL with asyncpg")
    if parsed_url.database is None or not parsed_url.database.endswith("_test"):
        raise RuntimeError("TEST_DATABASE_URL database name must end with '_test'")

    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.downgrade(alembic_config, "base")
        command.upgrade(alembic_config, "head")
        yield database_url
        command.downgrade(alembic_config, "base")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url


@pytest_asyncio.fixture
async def db_session(migrated_database_url: str) -> AsyncIterator[AsyncSession]:
    """Provide a clean transaction-capable session backed by PostgreSQL."""
    database = Database(migrated_database_url)
    async with database.engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE "
                "season_results, excluded_users, seasons, current_reactions, "
                "reaction_events, comments, posts, users, channels "
                "RESTART IDENTITY CASCADE",
            ),
        )

    try:
        async with database.session() as session:
            yield session
            await session.rollback()
    finally:
        await database.dispose()
