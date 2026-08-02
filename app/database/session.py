"""Asynchronous SQLAlchemy engine and session lifecycle."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)


class Database:
    """Own the SQLAlchemy engine and create isolated async sessions."""

    def __init__(self, url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            url,
            pool_pre_ping=True,
            connect_args={"server_settings": {"timezone": "UTC"}},
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        """Expose the engine for infrastructure integrations."""
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Yield a session and guarantee rollback and close on failure."""
        async with self._session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def check_connection(self) -> None:
        """Fail fast if PostgreSQL is unavailable."""
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        logger.info("PostgreSQL connection established")

    async def dispose(self) -> None:
        """Close the engine connection pool."""
        await self._engine.dispose()
        logger.info("PostgreSQL connection pool closed")
