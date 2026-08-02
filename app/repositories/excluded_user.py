"""Excluded user repository."""

from typing import cast

from sqlalchemy import select

from app.models.excluded_user import ExcludedUser
from app.repositories.base import BaseRepository


class ExcludedUserRepository(BaseRepository[ExcludedUser]):
    """Persistence operations for per-channel exclusions."""

    model: type[ExcludedUser] = ExcludedUser

    async def get_by_channel_and_user(
        self,
        channel_id: int,
        user_id: int,
    ) -> ExcludedUser | None:
        statement = select(ExcludedUser).where(
            ExcludedUser.channel_id == channel_id,
            ExcludedUser.user_id == user_id,
        )
        return cast("ExcludedUser | None", await self.session.scalar(statement))

    async def exclusion_exists(self, channel_id: int, user_id: int) -> bool:
        return await self.exists(
            ExcludedUser.channel_id == channel_id,
            ExcludedUser.user_id == user_id,
        )
