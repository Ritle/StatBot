"""Reusable Telegram-facing access checks for administrative handlers."""

from aiogram import Bot
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, Message

from app.bot.keyboards import channel_choice_keyboard
from app.config import Settings
from app.database.session import Database
from app.models import Channel
from app.repositories import ChannelRepository
from app.services.channel_access import ChannelAccessService


async def resolve_admin_channel(
    message: Message,
    *,
    action: str,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> Channel | None:
    """Resolve one manageable channel for an administrator command."""
    sender = message.from_user
    if sender is None:
        await message.answer("Не удалось определить администратора.")
        return None
    async with database.session() as session:
        access = ChannelAccessService(bot, session, settings)
        if message.chat.type == ChatType.PRIVATE:
            channels = await access.available_to_user(sender.id, admin_only=True)
            if not channels:
                await message.answer("Нет доступных каналов, которыми вы можете управлять.")
                return None
            if len(channels) > 1:
                await message.answer(
                    "Выберите канал:",
                    reply_markup=channel_choice_keyboard(channels, action),
                )
                return None
            return channels[0]
        channel = await access.from_chat(message.chat.id)
        if channel is None:
            await message.answer("Этот чат не связан с настроенным каналом.")
            return None
        if not await access.can_access(sender.id, channel, admin_only=True):
            await message.answer("Команда доступна только администраторам канала.")
            return None
        return channel


async def verify_admin_callback_channel(
    callback: CallbackQuery,
    channel_id: int,
    *,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> Channel | None:
    """Reload callback context and verify current administrator rights."""
    async with database.session() as session:
        channel = await ChannelRepository(session).get_by_id(channel_id)
        if channel is None:
            await callback.answer("Канал больше не доступен", show_alert=True)
            return None
        access = ChannelAccessService(bot, session, settings)
        if not await access.can_access(callback.from_user.id, channel, admin_only=True):
            await callback.answer("Недостаточно прав", show_alert=True)
            return None
        return channel
