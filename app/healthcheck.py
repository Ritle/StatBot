"""Container readiness probe for the PostgreSQL dependency."""

from __future__ import annotations

import asyncio
import os

from app.database.session import Database


async def check() -> None:
    """Exit unsuccessfully when the configured database is unavailable."""
    database_url = os.environ.get("DATABASE_URL")
    if not database_url or not database_url.startswith("postgresql+asyncpg://"):
        raise RuntimeError("DATABASE_URL is missing or invalid")
    database = Database(database_url)
    try:
        await database.check_connection(attempts=1)
    finally:
        await database.dispose()


def main() -> None:
    asyncio.run(check())


if __name__ == "__main__":
    main()
