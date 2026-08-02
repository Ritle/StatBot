"""Administrative channel/discussion discovery and persistence."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import ChatFullInfo
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.exceptions import SetupError, SetupPermissionError
from app.models import Channel
from app.repositories import ChannelRepository
from app.services.audit import AdminAction, AuditService
from app.services.permissions import BotPermissionReport, TelegramPermissionService


@dataclass(frozen=True, slots=True)
class SetupResult:
    """Saved configuration plus live permission diagnostics."""

    channel: Channel
    discussion_title: str
    permissions: BotPermissionReport


class ChannelSetupService:
    """Resolve a linked pair through Telegram IDs and save it atomically."""

    def __init__(self, bot: Bot, session: AsyncSession, settings: Settings) -> None:
        self.bot = bot
        self.session = session
        self.settings = settings
        self.permissions = TelegramPermissionService(bot, settings.superadmin_ids)

    async def setup(
        self,
        *,
        current_chat_id: int,
        actor_user_id: int,
        requested_chat_id: int | None = None,
    ) -> SetupResult:
        starting_chat = await self.bot.get_chat(requested_chat_id or current_chat_id)
        channel_info, discussion_info = await self._resolve_pair(starting_chat)

        allowed = await self.permissions.is_channel_administrator(
            actor_user_id,
            channel_info.id,
        )
        if not allowed:
            raise SetupPermissionError("команда доступна только администраторам канала")

        permission_report = await self.permissions.inspect_bot(
            channel_info.id,
            discussion_info.id,
        )
        repository = ChannelRepository(self.session)
        channel = await repository.upsert_settings(
            telegram_channel_id=channel_info.id,
            title=channel_info.title or str(channel_info.id),
            username=channel_info.username,
            discussion_chat_id=discussion_info.id,
            timezone=self.settings.default_timezone,
        )
        await AuditService(self.session).record(
            admin_id=actor_user_id,
            channel_id=channel.id,
            action=AdminAction.SETUP_CHANNEL,
            target_type="channel",
            target_id=channel.id,
            metadata={
                "telegram_channel_id": channel.telegram_channel_id,
                "discussion_chat_id": discussion_info.id,
            },
        )
        return SetupResult(
            channel=channel,
            discussion_title=discussion_info.title or str(discussion_info.id),
            permissions=permission_report,
        )

    async def _resolve_pair(
        self,
        chat: ChatFullInfo,
    ) -> tuple[ChatFullInfo, ChatFullInfo]:
        if chat.type == ChatType.CHANNEL:
            channel_info = chat
            if chat.linked_chat_id is None:
                raise SetupError("у канала не настроена связанная группа обсуждений")
            discussion_info = await self.bot.get_chat(chat.linked_chat_id)
        elif chat.type in {ChatType.GROUP, ChatType.SUPERGROUP}:
            discussion_info = chat
            if chat.linked_chat_id is None:
                raise SetupError("эта группа не связана с Telegram-каналом")
            channel_info = await self.bot.get_chat(chat.linked_chat_id)
        else:
            raise SetupError(
                "укажите Telegram ID канала/группы или перешлите сообщение из канала",
            )

        if channel_info.type != ChatType.CHANNEL:
            raise SetupError("связанный чат не является каналом")
        if discussion_info.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
            raise SetupError("связанный чат не является группой обсуждений")
        if discussion_info.linked_chat_id not in {None, channel_info.id}:
            raise SetupError("Telegram вернул противоречивую связь группы и канала")
        if channel_info.linked_chat_id not in {None, discussion_info.id}:
            raise SetupError("Telegram вернул противоречивую связь канала и группы")
        return channel_info, discussion_info
