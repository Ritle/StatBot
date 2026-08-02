"""Protected /exclude and /include administrative workflows."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from html import escape
from typing import TypedDict, cast

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.callbacks import ChannelChoiceCallback, ExclusionCallback
from app.bot.handlers.seasons import _channel_from_callback, _resolve_admin_channel
from app.bot.keyboards import exclusion_choice_keyboard
from app.bot.states import ExclusionStates
from app.config import Settings
from app.database.session import Database
from app.exceptions import AdminOperationError
from app.models import Channel, User
from app.repositories import UserRepository
from app.services.exclusions import ExclusionService

router = Router(name=__name__)
_TTL = timedelta(minutes=10)


class TelegramUserValues(TypedDict):
    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    is_bot: bool


def _command_payload(
    message: Message,
) -> tuple[str | None, str | None, TelegramUserValues | None]:
    text = message.text or ""
    parts = text.split(maxsplit=2)
    reason: str | None = None
    if message.reply_to_message is not None and message.reply_to_message.from_user is not None:
        if len(parts) >= 2:
            reason = text.split(maxsplit=1)[1].strip()
        user = message.reply_to_message.from_user
        return None, reason, _telegram_user_data(user)
    if len(parts) < 2:
        return None, None, None
    identifier = parts[1]
    if len(parts) == 3:
        reason = parts[2].strip()
    return identifier, reason, None


def _telegram_user_data(user: TelegramUser) -> TelegramUserValues:
    return {
        "telegram_user_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_bot": user.is_bot,
    }


async def _begin_exclusion_command(
    message: Message,
    action: str,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    identifier, reason, reply_user = _command_payload(message)
    if identifier is None and reply_user is None:
        await message.answer(
            f"Использование: /{action} <Telegram ID|@username>"
            + (" [причина] или reply на сообщение." if action == "exclude" else "."),
        )
        return
    token = secrets.token_hex(4)
    await state.set_state(ExclusionStates.choice)
    await state.set_data(
        {
            "stage": "channel",
            "action": action,
            "identifier": identifier,
            "reason": reason,
            "reply_user": reply_user,
            "token": token,
            "expires_at": (datetime.now(UTC) + _TTL).isoformat(),
        },
    )
    channel = await _resolve_admin_channel(
        message,
        action=action,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is not None:
        await _resolve_and_apply(message, state, channel, database)


@router.message(Command("exclude"))
async def exclude_command(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    await _begin_exclusion_command(message, "exclude", state, bot, database, settings)


@router.message(Command("include"))
async def include_command(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    await _begin_exclusion_command(message, "include", state, bot, database, settings)


@router.message(Command("cancel"), StateFilter(*ExclusionStates.__all_states__))
async def cancel_exclusion(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Операция с исключением отменена.")


@router.callback_query(ChannelChoiceCallback.filter(F.action.in_({"exclude", "include"})))
async def exclusion_channel_selected(
    callback: CallbackQuery,
    callback_data: ChannelChoiceCallback,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await _channel_from_callback(
        callback,
        callback_data.channel_id,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is None:
        return
    data = await state.get_data()
    if (
        await state.get_state() != ExclusionStates.choice.state
        or _expired(data)
        or data.get("stage") != "channel"
        or data.get("action") != callback_data.action
    ):
        await state.clear()
        await callback.answer("Сценарий устарел", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    await callback.answer()
    await _resolve_and_apply(
        callback.message,
        state,
        channel,
        database,
        telegram_admin=callback.from_user,
    )


async def _resolve_and_apply(
    message: Message,
    state: FSMContext,
    channel: Channel,
    database: Database,
    *,
    telegram_admin: TelegramUser | None = None,
) -> None:
    data = await state.get_data()
    if _expired(data):
        await state.clear()
        await message.answer("Сценарий истёк. Повторите команду.")
        return
    admin = telegram_admin or message.from_user
    if admin is None:
        await state.clear()
        await message.answer("Не удалось определить администратора.")
        return
    async with database.session() as session, session.begin():
        users = UserRepository(session)
        reply_data = data.get("reply_user")
        if isinstance(reply_data, dict):
            target = await users.upsert_telegram_user(
                **cast("TelegramUserValues", reply_data),
            )
            matches = [target]
        else:
            matches = await ExclusionService(session).find_known_users(str(data["identifier"]))
    if not matches:
        await state.clear()
        await message.answer(
            "Пользователь не известен боту. Username ищется только в локальной базе; "
            "глобального поиска Telegram Bot API не существует.",
        )
        return
    if len(matches) > 1:
        await state.update_data(stage="user", channel_id=channel.id)
        await message.answer(
            "Найдено несколько известных профилей. Выберите нужный:",
            reply_markup=exclusion_choice_keyboard(
                channel.id,
                matches,
                str(data["action"]),
                str(data["token"]),
            ),
        )
        return
    await _apply_exclusion(
        message,
        state,
        channel,
        matches[0],
        admin,
        database,
    )


@router.callback_query(ExclusionCallback.filter())
async def exclusion_user_selected(
    callback: CallbackQuery,
    callback_data: ExclusionCallback,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await _channel_from_callback(
        callback,
        callback_data.channel_id,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is None:
        return
    data = await state.get_data()
    if (
        await state.get_state() != ExclusionStates.choice.state
        or _expired(data)
        or data.get("stage") != "user"
        or callback_data.token != data.get("token")
        or callback_data.action not in {str(data.get("action")), "cancel"}
        or callback_data.channel_id != int(data.get("channel_id", 0))
    ):
        await state.clear()
        await callback.answer("Кнопка устарела", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        return
    if callback_data.action == "cancel":
        await state.clear()
        await callback.answer("Отменено")
        await callback.message.edit_reply_markup(reply_markup=None)
        return
    async with database.session() as session:
        user = await UserRepository(session).get_by_id(callback_data.user_id)
    if user is None:
        await state.clear()
        await callback.answer("Профиль больше не доступен", show_alert=True)
        return
    await callback.answer()
    await _apply_exclusion(
        callback.message,
        state,
        channel,
        user,
        callback.from_user,
        database,
    )


async def _apply_exclusion(
    message: Message,
    state: FSMContext,
    channel: Channel,
    target: User,
    admin: TelegramUser,
    database: Database,
) -> None:
    data = await state.get_data()
    action = str(data["action"])
    try:
        async with database.session() as session, session.begin():
            users = UserRepository(session)
            admin_user = await users.upsert_telegram_user(**_telegram_user_data(admin))
            stored_target = await users.get_by_id(target.id)
            if stored_target is None:
                raise AdminOperationError("пользователь больше не доступен")
            service = ExclusionService(session)
            if action == "exclude":
                await service.exclude(
                    channel_id=channel.id,
                    user=stored_target,
                    admin_user=admin_user,
                    telegram_admin_id=admin.id,
                    reason=str(data["reason"]) if data.get("reason") else None,
                )
                result = "Пользователь исключён из будущих пересчётов активного рейтинга."
            else:
                removed = await service.include(
                    channel_id=channel.id,
                    user=stored_target,
                    telegram_admin_id=admin.id,
                )
                result = (
                    "Пользователь возвращён в рейтинг."
                    if removed
                    else "Пользователь не был исключён."
                )
    except AdminOperationError as error:
        await message.answer(f"Операция не выполнена: {escape(str(error))}")
        return
    await state.clear()
    await message.answer(
        result + " Завершённые периоды автоматически не изменяются.",
    )


def _expired(data: dict[str, object]) -> bool:
    value = data.get("expires_at")
    if value is None:
        return True
    try:
        return datetime.fromisoformat(str(value)) < datetime.now(UTC)
    except (TypeError, ValueError):
        return True
