"""Shared asynchronous repository primitives."""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute
from sqlalchemy.sql.elements import ColumnElement

from app.database.base import Base


class BaseRepository[ModelT: Base]:
    """Small persistence abstraction; transaction ownership stays with services."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, entity_id: int) -> ModelT | None:
        """Return an entity by its internal identifier."""
        return await self.session.get(self.model, entity_id)

    async def create(self, **values: Any) -> ModelT:
        """Create and flush an entity without committing the transaction."""
        entity = self.model(**values)
        return await self.save(entity)

    async def save(self, entity: ModelT) -> ModelT:
        """Attach and flush an entity without committing the transaction."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def update(self, entity: ModelT, **values: Any) -> ModelT:
        """Apply explicit field values and flush the entity."""
        for field_name, value in values.items():
            if not hasattr(entity, field_name):
                raise AttributeError(
                    f"{type(entity).__name__} has no mapped field {field_name!r}",
                )
            setattr(entity, field_name, value)
        return await self.save(entity)

    async def exists(self, *criteria: ColumnElement[bool]) -> bool:
        """Return whether a row satisfies all supplied SQL criteria."""
        statement = select(exists().where(*criteria))
        return bool(await self.session.scalar(statement))

    async def exists_by_id(self, entity_id: int) -> bool:
        """Return whether an entity exists by internal identifier."""
        id_column = cast(
            "InstrumentedAttribute[int]",
            vars(self.model)["id"],
        )
        return await self.exists(id_column == entity_id)
