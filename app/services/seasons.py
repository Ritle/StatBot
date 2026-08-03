"""Transactional rating-period lifecycle operations."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SeasonError
from app.models import Season, SeasonStatus
from app.repositories import SeasonRepository, SeasonResultRepository
from app.schemas import RatingEntry
from app.services.audit import AdminAction, AuditService
from app.services.rating import RatingService

_MAX_INTEGER_SETTING = 2_147_483_647


class SeasonService:
    """Validate lifecycle transitions and freeze final rating snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.seasons = SeasonRepository(session)
        self.results = SeasonResultRepository(session)
        self.rating = RatingService(session)
        self.audit = AuditService(session)

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
        actor_user_id: int | None = None,
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
        if not all(
            0 <= value <= _MAX_INTEGER_SETTING
            for value in (comment_points, reaction_points, minimum_comment_length)
        ):
            raise SeasonError("баллы и минимальная длина выходят за допустимый диапазон")
        if daily_comment_limit is not None and daily_comment_limit <= 0:
            raise SeasonError("дневной лимит должен быть положительным или отключён")
        if daily_comment_limit is not None and daily_comment_limit > _MAX_INTEGER_SETTING:
            raise SeasonError("дневной лимит выходит за допустимый диапазон")
        season = await self.seasons.create(
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
        if actor_user_id is not None:
            await self.audit.record(
                admin_id=actor_user_id,
                channel_id=channel_id,
                action=AdminAction.CREATE_SEASON,
                target_type="season",
                target_id=season.id,
            )
        return season

    async def start(self, season_id: int, *, actor_user_id: int | None = None) -> Season:
        season = await self.seasons.get_locked(season_id)
        if season is None:
            raise SeasonError("период не найден")
        if season.status != SeasonStatus.DRAFT:
            raise SeasonError("активировать можно только черновик")
        if await self.seasons.active_exists(season.channel_id):
            raise SeasonError("для канала уже существует активный период")
        season = await self.seasons.update(season, status=SeasonStatus.ACTIVE)
        if actor_user_id is not None:
            await self.audit.record(
                admin_id=actor_user_id,
                channel_id=season.channel_id,
                action=AdminAction.START_SEASON,
                target_type="season",
                target_id=season.id,
            )
        return season

    async def cancel(self, season_id: int, *, actor_user_id: int | None = None) -> Season:
        season = await self.seasons.get_locked(season_id)
        if season is None:
            raise SeasonError("период не найден")
        if season.status not in {SeasonStatus.DRAFT, SeasonStatus.ACTIVE}:
            raise SeasonError("отменить можно только черновик или активный период")
        season = await self.seasons.update(season, status=SeasonStatus.CANCELLED)
        if actor_user_id is not None:
            await self.audit.record(
                admin_id=actor_user_id,
                channel_id=season.channel_id,
                action=AdminAction.CANCEL_SEASON,
                target_type="season",
                target_id=season.id,
            )
        return season

    async def finish(
        self,
        season_id: int,
        *,
        timezone: str,
        finished_at: datetime | None = None,
        actor_user_id: int | None = None,
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
        if actor_user_id is not None:
            await self.audit.record(
                admin_id=actor_user_id,
                channel_id=season.channel_id,
                action=AdminAction.FINISH_SEASON,
                target_type="season",
                target_id=season.id,
                metadata={"participants": len(entries)},
            )
        return season, entries

    async def recalculate_active(
        self,
        channel_id: int,
        *,
        timezone: str,
        expected_season_id: int | None = None,
        actor_user_id: int | None = None,
    ) -> tuple[Season, tuple[RatingEntry, ...]]:
        season = await self.seasons.get_active_by_channel_id(channel_id)
        if season is None:
            raise SeasonError("у канала нет активного периода")
        if expected_season_id is not None and season.id != expected_season_id:
            raise SeasonError("кнопка относится к другому активному периоду")
        entries = await self.rating.get_all(season, timezone=timezone)
        if actor_user_id is not None:
            await self.audit.record(
                admin_id=actor_user_id,
                channel_id=season.channel_id,
                action=AdminAction.RECALCULATE,
                target_type="season",
                target_id=season.id,
                metadata={"participants": len(entries)},
            )
        return season, entries

    async def update_rules(
        self,
        season_id: int,
        *,
        actor_user_id: int,
        confirmed_active: bool,
        comment_points: int | None = None,
        reaction_points: int | None = None,
        daily_comment_limit: int | None | object = ...,
        minimum_comment_length: int | None = None,
    ) -> Season:
        """Change scoring rules while preserving finalized snapshots."""
        season = await self.seasons.get_locked(season_id)
        if season is None:
            raise SeasonError("период не найден")
        if season.status == SeasonStatus.FINISHED:
            raise SeasonError("правила завершённого периода изменять нельзя")
        if season.status == SeasonStatus.CANCELLED:
            raise SeasonError("правила отменённого периода изменять нельзя")
        if season.status == SeasonStatus.ACTIVE and not confirmed_active:
            raise SeasonError("изменение активного периода требует подтверждения")

        changes: dict[str, object] = {}
        if comment_points is not None:
            if not 0 <= comment_points <= _MAX_INTEGER_SETTING:
                raise SeasonError("баллы выходят за допустимый диапазон")
            changes["comment_points"] = comment_points
        if reaction_points is not None:
            if not 0 <= reaction_points <= _MAX_INTEGER_SETTING:
                raise SeasonError("баллы выходят за допустимый диапазон")
            changes["reaction_points"] = reaction_points
        if minimum_comment_length is not None:
            if not 0 <= minimum_comment_length <= _MAX_INTEGER_SETTING:
                raise SeasonError("минимальная длина выходит за допустимый диапазон")
            changes["minimum_comment_length"] = minimum_comment_length
        if daily_comment_limit is not ...:
            if daily_comment_limit is not None and (
                not isinstance(daily_comment_limit, int)
                or daily_comment_limit <= 0
                or daily_comment_limit > _MAX_INTEGER_SETTING
            ):
                raise SeasonError("дневной лимит должен быть положительным или отключён")
            changes["daily_comment_limit"] = daily_comment_limit
        if not changes:
            raise SeasonError("не передано ни одного изменения")
        season = await self.seasons.update(season, **changes)
        await self.audit.record(
            admin_id=actor_user_id,
            channel_id=season.channel_id,
            action=AdminAction.UPDATE_RULES,
            target_type="season",
            target_id=season.id,
            metadata={"fields": sorted(changes)},
        )
        return season
