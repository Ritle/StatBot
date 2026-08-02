"""Transactional rating-period lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SeasonError
from app.models import Season, SeasonStatus
from app.repositories import SeasonRepository, SeasonResultRepository
from app.schemas import RatingEntry
from app.services.rating import RatingService


class SeasonService:
    """Validate lifecycle transitions and freeze final rating snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.seasons = SeasonRepository(session)
        self.results = SeasonResultRepository(session)
        self.rating = RatingService(session)

    async def create_draft(
        self,
        *,
        channel_id: int,
        name: str,
        starts_at: datetime,
        ends_at: datetime,
        comment_points: int,
        reaction_points: int,
        daily_comment_limit: int | None,
        minimum_comment_length: int,
    ) -> Season:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 255:
            raise SeasonError("название должно содержать от 1 до 255 символов")
        if starts_at.tzinfo is None or ends_at.tzinfo is None:
            raise SeasonError("даты периода должны содержать часовой пояс")
        starts_at = starts_at.astimezone(UTC)
        ends_at = ends_at.astimezone(UTC)
        if ends_at <= starts_at:
            raise SeasonError("окончание периода должно быть позже начала")
        if comment_points < 0 or reaction_points < 0 or minimum_comment_length < 0:
            raise SeasonError("баллы и минимальная длина не могут быть отрицательными")
        if daily_comment_limit is not None and daily_comment_limit <= 0:
            raise SeasonError("дневной лимит должен быть положительным или отключён")
        return await self.seasons.create(
            channel_id=channel_id,
            name=normalized_name,
            starts_at=starts_at,
            ends_at=ends_at,
            status=SeasonStatus.DRAFT,
            comment_points=comment_points,
            reaction_points=reaction_points,
            daily_comment_limit=daily_comment_limit,
            minimum_comment_length=minimum_comment_length,
        )

    async def start(self, season_id: int) -> Season:
        season = await self.seasons.get_locked(season_id)
        if season is None:
            raise SeasonError("период не найден")
        if season.status != SeasonStatus.DRAFT:
            raise SeasonError("активировать можно только черновик")
        if await self.seasons.active_exists(season.channel_id):
            raise SeasonError("для канала уже существует активный период")
        return await self.seasons.update(season, status=SeasonStatus.ACTIVE)

    async def cancel(self, season_id: int) -> Season:
        season = await self.seasons.get_locked(season_id)
        if season is None:
            raise SeasonError("период не найден")
        if season.status not in {SeasonStatus.DRAFT, SeasonStatus.ACTIVE}:
            raise SeasonError("отменить можно только черновик или активный период")
        return await self.seasons.update(season, status=SeasonStatus.CANCELLED)

    async def finish(
        self,
        season_id: int,
        *,
        timezone: str,
        finished_at: datetime | None = None,
    ) -> tuple[Season, tuple[RatingEntry, ...]]:
        season = await self.seasons.get_locked(season_id)
        if season is None:
            raise SeasonError("период не найден")
        if season.status != SeasonStatus.ACTIVE:
            raise SeasonError("завершить можно только активный период")
        now = (finished_at or datetime.now(UTC)).astimezone(UTC)
        if now <= season.starts_at:
            raise SeasonError("период ещё не начался")
        if now < season.ends_at:
            season.ends_at = now
        entries = await self.rating.get_all(season, timezone=timezone)
        await self.results.replace_for_season(
            season.id,
            (
                {
                    "user_id": entry.user_id,
                    "position": entry.position,
                    "score": entry.score,
                    "total_comments": entry.total_comments,
                    "counted_comments": entry.counted_comments,
                    "reactions": entry.reactions,
                    "active_days": entry.active_days,
                    "first_activity_at": entry.first_activity_at,
                }
                for entry in entries
            ),
        )
        season = await self.seasons.update(
            season,
            status=SeasonStatus.FINISHED,
            finished_at=now,
        )
        return season, entries

    async def recalculate_active(
        self,
        channel_id: int,
        *,
        timezone: str,
        expected_season_id: int | None = None,
    ) -> tuple[Season, tuple[RatingEntry, ...]]:
        season = await self.seasons.get_active_by_channel_id(channel_id)
        if season is None:
            raise SeasonError("у канала нет активного периода")
        if expected_season_id is not None and season.id != expected_season_id:
            raise SeasonError("кнопка относится к другому активному периоду")
        return season, await self.rating.get_all(season, timezone=timezone)
