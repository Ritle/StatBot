"""Read-only diagnostics for a configured Telegram channel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from sqlalchemy import func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions import SetupError, SetupPermissionError
from app.models import Channel, Comment, CurrentReaction, Post, ReactionEvent, Season
from app.repositories import ChannelRepository, SeasonRepository
from app.services.permissions import BotPermissionReport, TelegramPermissionService


@dataclass(frozen=True, slots=True)
class ChannelStatus:
    channel: Channel
    discussion_title: str
    permissions: BotPermissionReport
    administrator_ok: bool
    active_season: Season | None
    user_count: int
    post_count: int
    comment_count: int
    reaction_count: int
    last_event_at: datetime | None


class ChannelStatusService:
    """Collect database counters and fresh Telegram permission information."""

    def __init__(self, bot: Bot, session: AsyncSession, settings: Settings) -> None:
        self.bot = bot
        self.session = session
        self.channels = ChannelRepository(session)
        self.seasons = SeasonRepository(session)
        self.permissions = TelegramPermissionService(bot, settings.superadmin_ids)

    async def get_status(
        self,
        *,
        current_chat_id: int,
        actor_user_id: int,
        requested_chat_id: int | None = None,
    ) -> ChannelStatus:
        lookup_id = requested_chat_id or current_chat_id
        channel = await self.channels.get_by_telegram_id(lookup_id)
        if channel is None:
            channel = await self.channels.get_by_discussion_chat_id(lookup_id)
        if channel is None or channel.discussion_chat_id is None:
            raise SetupError("канал или группа ещё не настроены; выполните /setup")
        if not await self.permissions.is_channel_administrator(
            actor_user_id,
            channel.telegram_channel_id,
        ):
            raise SetupPermissionError("команда доступна только администраторам канала")

        bot_permissions = await self.permissions.inspect_bot(
            channel.telegram_channel_id,
            channel.discussion_chat_id,
        )
        active_season = await self.seasons.get_active_by_channel_id(channel.id)
        user_ids = union(
            select(Comment.user_id).where(Comment.channel_id == channel.id),
            select(CurrentReaction.user_id).where(CurrentReaction.channel_id == channel.id),
        ).subquery()
        user_count = int(
            await self.session.scalar(select(func.count()).select_from(user_ids)) or 0
        )
        post_count = int(
            await self.session.scalar(
                select(func.count()).select_from(Post).where(Post.channel_id == channel.id),
            )
            or 0
        )
        comment_count = int(
            await self.session.scalar(
                select(func.count()).select_from(Comment).where(Comment.channel_id == channel.id),
            )
            or 0
        )
        reaction_count = int(
            await self.session.scalar(
                select(func.count())
                .select_from(CurrentReaction)
                .where(CurrentReaction.channel_id == channel.id),
            )
            or 0
        )
        last_post = await self.session.scalar(
            select(func.max(Post.published_at)).where(Post.channel_id == channel.id),
        )
        last_comment = await self.session.scalar(
            select(func.max(Comment.created_at)).where(Comment.channel_id == channel.id),
        )
        last_reaction = await self.session.scalar(
            select(func.max(ReactionEvent.created_at)).where(
                ReactionEvent.channel_id == channel.id,
            ),
        )
        candidates = [
            value for value in (last_post, last_comment, last_reaction) if value is not None
        ]
        discussion = await self.bot.get_chat(channel.discussion_chat_id)
        return ChannelStatus(
            channel=channel,
            discussion_title=discussion.title or str(discussion.id),
            permissions=bot_permissions,
            administrator_ok=True,
            active_season=active_season,
            user_count=user_count,
            post_count=post_count,
            comment_count=comment_count,
            reaction_count=reaction_count,
            last_event_at=max(candidates) if candidates else None,
        )
