"""Resolve command scope in discussion groups and private chats."""

from __future__ import annotations

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Channel
from app.repositories import ChannelRepository
from app.services.permissions import TelegramPermissionService


class ChannelAccessService:
    """Find channel contexts without introducing a global active channel."""

    def __init__(
        self,
        bot: Bot,
        session: AsyncSession,
        settings: Settings,
    ) -> None:
        self.bot = bot
        self.channels = ChannelRepository(session)
        self.permissions = TelegramPermissionService(bot, settings.superadmin_ids)

    async def from_chat(self, chat_id: int) -> Channel | None:
        channel = await self.channels.get_by_discussion_chat_id(chat_id)
        if channel is None:
            channel = await self.channels.get_by_telegram_id(chat_id)
        return channel

    async def available_to_user(self, user_id: int, *, admin_only: bool) -> list[Channel]:
        channels = await self.channels.list_active()
        available: list[Channel] = []
        for channel in channels:
            if admin_only:
                allowed = await self.permissions.is_channel_administrator(
                    user_id,
                    channel.telegram_channel_id,
                )
            else:
                allowed = await self._is_discussion_member(user_id, channel)
            if allowed:
                available.append(channel)
        return available

    async def can_access(self, user_id: int, channel: Channel, *, admin_only: bool) -> bool:
        if admin_only:
            return await self.permissions.is_channel_administrator(
                user_id,
                channel.telegram_channel_id,
            )
        return await self._is_discussion_member(user_id, channel)

    async def _is_discussion_member(self, user_id: int, channel: Channel) -> bool:
        if channel.discussion_chat_id is None:
            return False
        try:
            member = await self.bot.get_chat_member(channel.discussion_chat_id, user_id)
        except TelegramAPIError:
            return False
        return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED}
