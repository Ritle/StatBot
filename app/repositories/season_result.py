"""Season result repository."""

from collections.abc import Iterable
from typing import cast

from sqlalchemy import delete, select

from app.models.season_result import SeasonResult
from app.repositories.base import BaseRepository


class SeasonResultRepository(BaseRepository[SeasonResult]):
    """Persistence operations for persisted season results."""

    model: type[SeasonResult] = SeasonResult

    async def get_by_season_and_user(
        self,
        season_id: int,
        user_id: int,
    ) -> SeasonResult | None:
        statement = select(SeasonResult).where(
            SeasonResult.season_id == season_id,
            SeasonResult.user_id == user_id,
        )
        return cast("SeasonResult | None", await self.session.scalar(statement))

    async def result_exists(self, season_id: int, user_id: int) -> bool:
        return await self.exists(
            SeasonResult.season_id == season_id,
            SeasonResult.user_id == user_id,
        )

    async def replace_for_season(
        self,
        season_id: int,
        rows: Iterable[dict[str, object]],
    ) -> None:
        """Replace a not-yet-published snapshot inside the caller's transaction."""
        await self.session.execute(
            delete(SeasonResult).where(SeasonResult.season_id == season_id),
        )
        self.session.add_all(SeasonResult(season_id=season_id, **row) for row in rows)
        await self.session.flush()
