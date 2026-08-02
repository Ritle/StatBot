"""Short-lived Telegram permission checks for administrative operations."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError


@dataclass(frozen=True, slots=True)
class BotPermissionReport:
    """Current bot membership and rights for a configured pair."""

    channel_ok: bool
    discussion_ok: bool
    problems: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return self.channel_ok and self.discussion_ok


class TelegramPermissionService:
    """Query Telegram directly so administrative rights never become stale."""

    def __init__(self, bot: Bot, superadmin_ids: frozenset[int]) -> None:
        self.bot = bot
        self.superadmin_ids = superadmin_ids

    async def is_channel_administrator(self, user_id: int, channel_id: int) -> bool:
        if user_id in self.superadmin_ids:
            return True
        try:
            member = await self.bot.get_chat_member(channel_id, user_id)
        except TelegramAPIError:
            return False
        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }

    async def inspect_bot(self, channel_id: int, discussion_chat_id: int) -> BotPermissionReport:
        bot_user = await self.bot.get_me()
        problems: list[str] = []
        channel_ok = await self._is_bot_admin(channel_id)
        if not channel_ok:
            problems.append("бот не является администратором канала")
        else:
            member = await self.bot.get_chat_member(channel_id, bot_user.id)
            if member.status == ChatMemberStatus.ADMINISTRATOR and not getattr(
                member,
                "can_post_messages",
                False,
            ):
                channel_ok = False
                problems.append("у бота нет права публикации сообщений в канале")

        discussion_ok = await self._is_bot_admin(discussion_chat_id)
        if not discussion_ok:
            problems.append("бот не является администратором группы обсуждений")
        return BotPermissionReport(channel_ok, discussion_ok, tuple(problems))

    async def _is_bot_admin(self, chat_id: int) -> bool:
        bot_user = await self.bot.get_me()
        try:
            member = await self.bot.get_chat_member(chat_id, bot_user.id)
        except TelegramAPIError:
            return False
        return member.status in {
            ChatMemberStatus.ADMINISTRATOR,
            ChatMemberStatus.CREATOR,
        }
