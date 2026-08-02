"""Season repository."""

from typing import cast

from sqlalchemy import select

from app.models.enums import SeasonStatus
from app.models.season import Season
from app.repositories.base import BaseRepository


class SeasonRepository(BaseRepository[Season]):
    """Persistence operations for rating seasons."""

    model: type[Season] = Season

    async def get_active_by_channel_id(self, channel_id: int) -> Season | None:
        statement = select(Season).where(
            Season.channel_id == channel_id,
            Season.status == SeasonStatus.ACTIVE,
        )
        return cast("Season | None", await self.session.scalar(statement))

    async def active_exists(self, channel_id: int) -> bool:
        return await self.exists(
            Season.channel_id == channel_id,
            Season.status == SeasonStatus.ACTIVE,
        )

    async def get_locked(self, season_id: int) -> Season | None:
        statement = select(Season).where(Season.id == season_id).with_for_update()
        return cast("Season | None", await self.session.scalar(statement))

    async def list_by_channel_id(self, channel_id: int) -> list[Season]:
        statement = (
            select(Season)
            .where(Season.channel_id == channel_id)
            .order_by(Season.starts_at.desc(), Season.id.desc())
        )
        return list((await self.session.scalars(statement)).all())

    async def list_drafts_by_channel_id(self, channel_id: int) -> list[Season]:
        statement = (
            select(Season)
            .where(
                Season.channel_id == channel_id,
                Season.status == SeasonStatus.DRAFT,
            )
            .order_by(Season.created_at.desc())
        )
        return list((await self.session.scalars(statement)).all())
