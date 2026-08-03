"""Administrative rating-period commands and creation FSM."""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.exc import IntegrityError

from app.bot.admin_access import resolve_admin_channel, verify_admin_callback_channel
from app.bot.callbacks import ChannelChoiceCallback, CreateSeasonCallback, SeasonActionCallback
from app.bot.keyboards import (
    confirmation_keyboard,
    create_confirmation_keyboard,
    season_action_keyboard,
)
from app.bot.states import SeasonCreateStates
from app.config import Settings
from app.database.session import Database
from app.exceptions import SeasonError
from app.models import Channel, Season, SeasonStatus
from app.repositories import ChannelRepository, SeasonRepository
from app.services.seasons import SeasonService
from app.utils.datetime import LocalTimeError, format_local_datetime, parse_local_datetime

logger = logging.getLogger(__name__)
router = Router(name=__name__)
_CREATION_TTL = timedelta(minutes=30)
_MAX_INTEGER_SETTING = 2_147_483_647

_ADMIN_CHANNEL_ACTIONS = {
    "create",
    "start",
    "finish",
    "cancel",
    "seasons",
    "period",
    "recalculate",
}


async def _begin_creation(message: Message, state: FSMContext, channel: Channel) -> None:
    await state.clear()
    await state.update_data(
        channel_id=channel.id,
        timezone=channel.timezone,
        expires_at=(datetime.now(UTC) + _CREATION_TTL).isoformat(),
    )
    await state.set_state(SeasonCreateStates.name)
    await message.answer(
        f"Создание периода для <b>{escape(channel.title)}</b>.\n"
        "Введите название (до 255 символов). Для отмены: /cancel.",
    )


@router.message(Command("create_season"))
async def create_season_command(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await resolve_admin_channel(
        message,
        action="create",
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is not None:
        await _begin_creation(message, state, channel)


@router.callback_query(
    ChannelChoiceCallback.filter(F.action.in_(_ADMIN_CHANNEL_ACTIONS)),
)
async def admin_channel_selected(
    callback: CallbackQuery,
    callback_data: ChannelChoiceCallback,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await verify_admin_callback_channel(
        callback,
        callback_data.channel_id,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is None or not isinstance(callback.message, Message):
        return
    await callback.answer()
    action = callback_data.action
    if action == "create":
        await _begin_creation(callback.message, state, channel)
    else:
        await _dispatch_admin_action(
            callback.message,
            channel,
            action,
            database,
            callback.from_user.id,
        )


@router.message(Command("cancel"), StateFilter(*SeasonCreateStates.__all_states__))
async def cancel_season_fsm(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание периода отменено.")


@router.message(SeasonCreateStates.name)
async def season_name(message: Message, state: FSMContext) -> None:
    if not await _creation_active(message, state):
        return
    name = (message.text or "").strip()
    if not name or len(name) > 255:
        await message.answer("Название должно содержать от 1 до 255 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(SeasonCreateStates.starts_at)
    await message.answer("Введите начало периода: ДД.ММ.ГГГГ ЧЧ:ММ.")


async def _parse_fsm_date(message: Message, state: FSMContext, key: str) -> datetime | None:
    if not await _creation_active(message, state):
        return None
    data = await state.get_data()
    try:
        value = parse_local_datetime(message.text or "", str(data["timezone"]))
    except LocalTimeError as error:
        await message.answer(f"Некорректная дата: {escape(str(error))}.")
        return None
    await state.update_data({key: value.isoformat()})
    return value


@router.message(SeasonCreateStates.starts_at)
async def season_starts_at(message: Message, state: FSMContext) -> None:
    if await _parse_fsm_date(message, state, "starts_at") is None:
        return
    await state.set_state(SeasonCreateStates.ends_at)
    await message.answer("Введите окончание периода: ДД.ММ.ГГГГ ЧЧ:ММ.")


@router.message(SeasonCreateStates.ends_at)
async def season_ends_at(message: Message, state: FSMContext) -> None:
    ends_at = await _parse_fsm_date(message, state, "ends_at")
    if ends_at is None:
        return
    data = await state.get_data()
    if ends_at <= datetime.fromisoformat(str(data["starts_at"])):
        await message.answer("Окончание должно быть позже начала.")
        return
    await state.set_state(SeasonCreateStates.comment_points)
    await message.answer("Сколько баллов начислять за зачтённый комментарий? (0 или больше)")


def _nonnegative_integer(value: str | None) -> int | None:
    try:
        parsed = int((value or "").strip())
    except ValueError:
        return None
    return parsed if 0 <= parsed <= _MAX_INTEGER_SETTING else None


@router.message(SeasonCreateStates.comment_points)
async def season_comment_points(message: Message, state: FSMContext) -> None:
    if not await _creation_active(message, state):
        return
    value = _nonnegative_integer(message.text)
    if value is None:
        await message.answer("Введите целое число 0 или больше.")
        return
    await state.update_data(comment_points=value)
    await state.set_state(SeasonCreateStates.reaction_points)
    await message.answer("Сколько баллов начислять за активную реакцию? (0 или больше)")


@router.message(SeasonCreateStates.reaction_points)
async def season_reaction_points(message: Message, state: FSMContext) -> None:
    if not await _creation_active(message, state):
        return
    value = _nonnegative_integer(message.text)
    if value is None:
        await message.answer("Введите целое число 0 или больше.")
        return
    await state.update_data(reaction_points=value)
    await state.set_state(SeasonCreateStates.daily_comment_limit)
    await message.answer("Дневной лимит комментариев: положительное число или «нет».")


@router.message(SeasonCreateStates.daily_comment_limit)
async def season_daily_limit(message: Message, state: FSMContext) -> None:
    if not await _creation_active(message, state):
        return
    raw = (message.text or "").strip().casefold()
    if raw in {"нет", "none", "без лимита", "0"}:
        value = None
    else:
        value = _nonnegative_integer(raw)
        if value is None or value == 0:
            await message.answer("Введите положительное число или «нет».")
            return
    await state.update_data(daily_comment_limit=value)
    await state.set_state(SeasonCreateStates.minimum_comment_length)
    await message.answer("Минимальная длина комментария: целое число 0 или больше.")


@router.message(SeasonCreateStates.minimum_comment_length)
async def season_minimum_length(message: Message, state: FSMContext) -> None:
    if not await _creation_active(message, state):
        return
    value = _nonnegative_integer(message.text)
    if value is None:
        await message.answer("Введите целое число 0 или больше.")
        return
    token = secrets.token_hex(4)
    await state.update_data(minimum_comment_length=value, confirmation_token=token)
    await state.set_state(SeasonCreateStates.confirmation)
    data = await state.get_data()
    timezone = str(data["timezone"])
    starts_at = datetime.fromisoformat(str(data["starts_at"]))
    ends_at = datetime.fromisoformat(str(data["ends_at"]))
    limit = data["daily_comment_limit"]
    await message.answer(
        "<b>Проверьте период</b>\n"
        f"Название: {escape(str(data['name']))}\n"
        f"Начало: {format_local_datetime(starts_at, timezone)}\n"
        f"Окончание: {format_local_datetime(ends_at, timezone)}\n"
        f"Баллы: комментарий {data['comment_points']}, реакция {data['reaction_points']}\n"
        f"Лимит в день: {limit if limit is not None else 'нет'}\n"
        f"Минимальная длина: {value}",
        reply_markup=create_confirmation_keyboard(token),
    )


@router.callback_query(CreateSeasonCallback.filter())
async def confirm_season_creation(
    callback: CallbackQuery,
    callback_data: CreateSeasonCallback,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    current_state = await state.get_state()
    data = await state.get_data()
    if current_state == SeasonCreateStates.confirmation.state and _creation_expired(data):
        await state.clear()
        await callback.answer("Сценарий создания периода истёк", show_alert=True)
        return
    if (
        current_state != SeasonCreateStates.confirmation.state
        or callback_data.token != data.get("confirmation_token")
    ):
        await callback.answer("Эта кнопка устарела", show_alert=True)
        return
    try:
        channel_id = int(data["channel_id"])
    except (KeyError, TypeError, ValueError):
        await state.clear()
        await callback.answer("Сценарий повреждён или устарел. Начните заново.", show_alert=True)
        return
    channel = await verify_admin_callback_channel(
        callback,
        channel_id,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is None:
        return
    if not callback_data.accept:
        await state.clear()
        await callback.answer("Отменено")
        if isinstance(callback.message, Message):
            await callback.message.edit_text("Создание периода отменено.")
        return
    try:
        name = str(data["name"])
        starts_at = datetime.fromisoformat(str(data["starts_at"]))
        ends_at = datetime.fromisoformat(str(data["ends_at"]))
        comment_points = int(data["comment_points"])
        reaction_points = int(data["reaction_points"])
        raw_limit = data["daily_comment_limit"]
        daily_comment_limit = int(raw_limit) if raw_limit is not None else None
        minimum_comment_length = int(data["minimum_comment_length"])
    except (KeyError, TypeError, ValueError):
        await state.clear()
        await callback.answer("Сценарий повреждён или устарел. Начните заново.", show_alert=True)
        return
    try:
        async with database.session() as session, session.begin():
            season = await SeasonService(session).create_draft(
                channel_id=channel.id,
                name=name,
                starts_at=starts_at,
                ends_at=ends_at,
                comment_points=comment_points,
                reaction_points=reaction_points,
                daily_comment_limit=daily_comment_limit,
                minimum_comment_length=minimum_comment_length,
                actor_user_id=callback.from_user.id,
            )
    except (SeasonError, IntegrityError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    await callback.answer("Создано")
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"Черновик <b>{escape(season.name)}</b> создан. ID: <code>{season.id}</code>.",
        )


async def _dispatch_admin_action(
    message: Message,
    channel: Channel,
    action: str,
    database: Database,
    actor_user_id: int,
) -> None:
    async with database.session() as session:
        repository = SeasonRepository(session)
        if action == "start":
            seasons = await repository.list_drafts_by_channel_id(channel.id)
            if not seasons:
                await message.answer("Нет черновиков для запуска.")
            elif len(seasons) == 1:
                try:
                    started = await SeasonService(session).start(
                        seasons[0].id,
                        actor_user_id=actor_user_id,
                    )
                    await session.commit()
                except (SeasonError, IntegrityError) as error:
                    await session.rollback()
                    await message.answer(f"Не удалось запустить период: {escape(str(error))}")
                else:
                    await message.answer(f"Период <b>{escape(started.name)}</b> активирован.")
            else:
                await message.answer(
                    "Выберите черновик:",
                    reply_markup=season_action_keyboard(seasons, "start"),
                )
        elif action == "finish":
            season = await repository.get_active_by_channel_id(channel.id)
            if season is None:
                await message.answer("Нет активного периода.")
            else:
                await message.answer(
                    f"Завершить <b>{escape(season.name)}</b> и зафиксировать рейтинг?",
                    reply_markup=confirmation_keyboard("finish", season.id),
                )
        elif action == "cancel":
            seasons = [
                season
                for season in await repository.list_by_channel_id(channel.id)
                if season.status in {SeasonStatus.DRAFT, SeasonStatus.ACTIVE}
            ]
            if not seasons:
                await message.answer("Нет периодов, доступных для отмены.")
            else:
                await message.answer(
                    "Выберите период:",
                    reply_markup=season_action_keyboard(seasons, "cancel_prompt"),
                )
        elif action == "seasons":
            await _show_seasons(message, channel, await repository.list_by_channel_id(channel.id))
        elif action == "period":
            season = await repository.get_active_by_channel_id(channel.id)
            await _show_period(message, channel, season)
        elif action == "recalculate":
            season = await repository.get_active_by_channel_id(channel.id)
            if season is None:
                await message.answer("Нет активного периода.")
            else:
                await message.answer(
                    f"Пересчитать <b>{escape(season.name)}</b> из исходных событий?",
                    reply_markup=confirmation_keyboard("recalculate", season.id),
                )


@router.message(Command("start_season"))
async def start_season_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_admin_message_action(message, "start", bot, database, settings)


@router.message(Command("finish_season"))
async def finish_season_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_admin_message_action(message, "finish", bot, database, settings)


@router.message(Command("cancel_season"))
async def cancel_season_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_admin_message_action(message, "cancel", bot, database, settings)


@router.message(Command("seasons"))
async def seasons_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_admin_message_action(message, "seasons", bot, database, settings)


@router.message(Command("period"))
async def period_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_admin_message_action(message, "period", bot, database, settings)


@router.message(Command("recalculate"))
async def recalculate_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_admin_message_action(message, "recalculate", bot, database, settings)


async def _run_admin_message_action(
    message: Message,
    action: str,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await resolve_admin_channel(
        message,
        action=action,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is not None:
        if message.from_user is not None:
            await _dispatch_admin_action(
                message,
                channel,
                action,
                database,
                message.from_user.id,
            )


@router.callback_query(SeasonActionCallback.filter())
async def season_action_callback(
    callback: CallbackQuery,
    callback_data: SeasonActionCallback,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    async with database.session() as session:
        season = await SeasonRepository(session).get_by_id(callback_data.season_id)
        if season is None:
            await callback.answer("Период не найден", show_alert=True)
            return
        channel = await ChannelRepository(session).get_by_id(season.channel_id)
    if channel is None:
        await callback.answer("Канал не найден", show_alert=True)
        return
    verified = await verify_admin_callback_channel(
        callback,
        channel.id,
        bot=bot,
        database=database,
        settings=settings,
    )
    if verified is None or not isinstance(callback.message, Message):
        return
    action = callback_data.action
    if action == "dismiss":
        await callback.answer("Отменено")
        await callback.message.edit_reply_markup(reply_markup=None)
        return
    if action == "cancel_prompt":
        await callback.answer()
        await callback.message.edit_text(
            f"Отменить период <b>{escape(season.name)}</b>? Данные не будут удалены.",
            reply_markup=confirmation_keyboard("cancel", season.id),
        )
        return
    try:
        async with database.session() as session, session.begin():
            service = SeasonService(session)
            if action == "start":
                changed = await service.start(
                    season.id,
                    actor_user_id=callback.from_user.id,
                )
                result_text = f"Период <b>{escape(changed.name)}</b> активирован."
            elif action == "cancel":
                changed = await service.cancel(
                    season.id,
                    actor_user_id=callback.from_user.id,
                )
                result_text = f"Период <b>{escape(changed.name)}</b> отменён."
            elif action == "finish":
                changed, entries = await service.finish(
                    season.id,
                    timezone=verified.timezone,
                    actor_user_id=callback.from_user.id,
                )
                result_text = (
                    f"Период <b>{escape(changed.name)}</b> завершён. "
                    f"Зафиксировано участников: {len(entries)}."
                )
            elif action == "recalculate":
                changed, entries = await service.recalculate_active(
                    verified.id,
                    timezone=verified.timezone,
                    expected_season_id=season.id,
                    actor_user_id=callback.from_user.id,
                )
                logger.info(
                    "Administrator %s recalculated active season %s for channel %s",
                    callback.from_user.id,
                    changed.id,
                    verified.id,
                )
                result_text = (
                    f"Период <b>{escape(changed.name)}</b> пересчитан из исходных событий. "
                    f"Участников: {len(entries)}. Завершённые результаты не изменялись."
                )
            else:
                await callback.answer("Неизвестное действие", show_alert=True)
                return
    except (SeasonError, IntegrityError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await callback.answer("Готово")
    await callback.message.edit_text(result_text)


async def _show_seasons(message: Message, channel: Channel, seasons: list[Season]) -> None:
    if not seasons:
        await message.answer("У канала пока нет периодов.")
        return
    lines = [f"<b>Периоды: {escape(channel.title)}</b>"]
    for season in seasons[:20]:
        lines.append(
            f"• <code>{season.id}</code> · {escape(season.name)} — {season.status.value}\n"
            f"  {format_local_datetime(season.starts_at, channel.timezone)} — "
            f"{format_local_datetime(season.ends_at, channel.timezone)}",
        )
    await message.answer("\n".join(lines))


async def _show_period(message: Message, channel: Channel, season: Season | None) -> None:
    if season is None:
        await message.answer("У канала нет активного периода.")
        return
    limit = season.daily_comment_limit if season.daily_comment_limit is not None else "нет"
    await message.answer(
        f"<b>{escape(season.name)}</b>\n"
        f"{format_local_datetime(season.starts_at, channel.timezone)} — "
        f"{format_local_datetime(season.ends_at, channel.timezone)}\n"
        f"Баллы: 💬 {season.comment_points}, 👍 {season.reaction_points}\n"
        f"Лимит комментариев в день: {limit}\n"
        f"Минимальная длина: {season.minimum_comment_length}",
    )


def _creation_expired(data: dict[str, object]) -> bool:
    value = data.get("expires_at")
    if value is None:
        return True
    try:
        return datetime.fromisoformat(str(value)) < datetime.now(UTC)
    except (TypeError, ValueError):
        return True


async def _creation_active(message: Message, state: FSMContext) -> bool:
    if not _creation_expired(await state.get_data()):
        return True
    await state.clear()
    await message.answer("Сценарий создания периода истёк. Запустите /create_season заново.")
    return False
