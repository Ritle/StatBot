"""Administrative setup and diagnostics commands."""

from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, MessageOriginChannel
from sqlalchemy.exc import IntegrityError

from app.bot.states.setup import SetupStates
from app.config import Settings
from app.database.session import Database
from app.exceptions import SetupError
from app.services.channel_setup import ChannelSetupService, SetupResult
from app.services.status import ChannelStatus, ChannelStatusService

router = Router(name=__name__)


def _command_chat_id(message: Message) -> int | None:
    text = message.text or message.caption or ""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return None
    try:
        return int(parts[1].strip())
    except ValueError:
        return None


def _forwarded_channel_id(message: Message) -> int | None:
    if isinstance(message.forward_origin, MessageOriginChannel):
        return message.forward_origin.chat.id
    return None


async def _perform_setup(
    message: Message,
    bot: Bot,
    database: Database,
    settings: Settings,
    requested_chat_id: int | None,
) -> bool:
    if message.from_user is None:
        await message.answer(
            "Не удалось определить пользователя. Запустите /setup из группы обсуждений "
            "или личного чата.",
        )
        return False
    try:
        async with database.session() as session, session.begin():
            result = await ChannelSetupService(bot, session, settings).setup(
                current_chat_id=message.chat.id,
                actor_user_id=message.from_user.id,
                requested_chat_id=requested_chat_id,
            )
    except (SetupError, TelegramAPIError, IntegrityError) as error:
        await message.answer(f"Настройка не завершена: {escape(str(error))}")
        return False
    await message.answer(_format_setup_result(result))
    return True


def _format_setup_result(result: SetupResult) -> str:
    channel = result.channel
    lines = [
        "<b>Настройка сохранена</b>",
        f"Канал: {escape(channel.title)} (<code>{channel.telegram_channel_id}</code>)",
        f"Обсуждения: {escape(result.discussion_title)} "
        f"(<code>{channel.discussion_chat_id}</code>)",
    ]
    if result.permissions.problems:
        lines.append("\n<b>Нужно исправить:</b>")
        lines.extend(f"• {escape(problem)}" for problem in result.permissions.problems)
    else:
        lines.append("\nПрава бота проверены: всё готово к сбору комментариев.")
    return "\n".join(lines)


@router.message(Command("setup"))
async def handle_setup(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    requested_chat_id = _command_chat_id(message)
    if message.chat.type == ChatType.PRIVATE and requested_chat_id is None:
        await state.set_state(SetupStates.waiting_for_chat)
        await message.answer(
            "Пришлите числовой Telegram ID канала/группы или перешлите сообщение "
            "из канала. Username не используется как идентификатор. Для отмены: /cancel.",
        )
        return
    await state.clear()
    await _perform_setup(message, bot, database, settings, requested_chat_id)


@router.message(SetupStates.waiting_for_chat, Command("cancel"))
async def cancel_setup(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Настройка отменена.")


@router.message(SetupStates.waiting_for_chat, F.chat.type == ChatType.PRIVATE)
async def continue_setup(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    requested_chat_id = _forwarded_channel_id(message)
    if requested_chat_id is None:
        try:
            requested_chat_id = int((message.text or "").strip())
        except ValueError:
            await message.answer("Нужен числовой Telegram ID или пересланное сообщение из канала.")
            return
    if await _perform_setup(message, bot, database, settings, requested_chat_id):
        await state.clear()


@router.message(Command("status"))
async def handle_status(
    message: Message,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить администратора.")
        return
    try:
        async with database.session() as session:
            status = await ChannelStatusService(bot, session, settings).get_status(
                current_chat_id=message.chat.id,
                actor_user_id=message.from_user.id,
                requested_chat_id=_command_chat_id(message),
            )
    except (SetupError, TelegramAPIError) as error:
        await message.answer(f"Статус недоступен: {escape(str(error))}")
        return
    await message.answer(_format_status(status))


def _format_status(status: ChannelStatus) -> str:
    channel = status.channel
    last_event = status.last_event_at.isoformat() if status.last_event_at else "событий ещё нет"
    warnings = list(status.permissions.problems)
    if not channel.is_active:
        warnings.append("сбор событий для канала выключен")
    lines = [
        "<b>Статус канала</b>",
        f"Канал: {escape(channel.title)} (<code>{channel.telegram_channel_id}</code>)",
        f"Обсуждения: {escape(status.discussion_title)} "
        f"(<code>{channel.discussion_chat_id}</code>)",
        f"Права бота: {'в порядке' if status.permissions.ok else 'требуют внимания'}",
        f"Активный период: {'есть' if status.has_active_season else 'нет'}",
        f"Публикаций: {status.post_count}",
        f"Комментариев: {status.comment_count}",
        f"Последнее событие: {escape(last_event)}",
    ]
    if warnings:
        lines.append("\n<b>Предупреждения:</b>")
        lines.extend(f"• {escape(item)}" for item in warnings)
    return "\n".join(lines)
