"""Public leaderboard, personal statistics and pagination commands."""

from __future__ import annotations

import math
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.bot.callbacks import ChannelChoiceCallback, RatingCallback
from app.bot.keyboards import channel_choice_keyboard, rating_keyboard
from app.config import Settings
from app.database.session import Database
from app.models import Channel, Season, SeasonStatus
from app.repositories import ChannelRepository, SeasonRepository
from app.schemas import RatingEntry, RatingOrder, RatingPage
from app.services.channel_access import ChannelAccessService
from app.services.rating import RatingService
from app.utils.datetime import format_local_datetime

router = Router(name=__name__)
_USER_ACTIONS = {"rating", "me", "comments", "reactions"}


def _split_action(value: str) -> tuple[str, int | None]:
    action, separator, raw_season_id = value.partition(":")
    if action not in _USER_ACTIONS:
        return value, None
    if not separator:
        return action, None
    try:
        return action, int(raw_season_id)
    except ValueError:
        return value, None


def _season_argument(message: Message) -> int | None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        return None
    try:
        return int(parts[1])
    except ValueError:
        return None


async def _resolve_user_channel(
    message: Message,
    *,
    action: str,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> Channel | None:
    sender = message.from_user
    if sender is None:
        await message.answer("Не удалось определить пользователя.")
        return None
    async with database.session() as session:
        access = ChannelAccessService(bot, session, settings)
        if message.chat.type == ChatType.PRIVATE:
            channels = await access.available_to_user(sender.id, admin_only=False)
            if not channels:
                await message.answer("Нет доступных настроенных каналов.")
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
            await message.answer("Эта группа не связана с настроенным каналом.")
        return channel


async def _run_rating_command(
    message: Message,
    action: str,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    requested_season_id = _season_argument(message)
    choice_action = f"{action}:{requested_season_id}" if requested_season_id else action
    channel = await _resolve_user_channel(
        message,
        action=choice_action,
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is not None:
        await _render_action(
            message,
            channel,
            action,
            database,
            telegram_user_id=message.from_user.id if message.from_user else None,
            requested_season_id=requested_season_id,
        )


@router.message(Command("rating"))
async def rating_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_rating_command(message, "rating", bot, database, settings)


@router.message(Command("me"))
async def me_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_rating_command(message, "me", bot, database, settings)


@router.message(Command("top_comments"))
async def top_comments_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_rating_command(message, "comments", bot, database, settings)


@router.message(Command("top_reactions"))
async def top_reactions_command(
    message: Message, bot: Bot, database: Database, settings: Settings
) -> None:
    await _run_rating_command(message, "reactions", bot, database, settings)


@router.callback_query(ChannelChoiceCallback.filter())
async def user_channel_selected(
    callback: CallbackQuery,
    callback_data: ChannelChoiceCallback,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    action, requested_season_id = _split_action(callback_data.action)
    if action not in _USER_ACTIONS:
        await callback.answer("Кнопка устарела", show_alert=True)
        return
    async with database.session() as session:
        channel = await ChannelRepository(session).get_by_id(callback_data.channel_id)
        if channel is None:
            await callback.answer("Канал не найден", show_alert=True)
            return
        access = ChannelAccessService(bot, session, settings)
        if not await access.can_access(callback.from_user.id, channel, admin_only=False):
            await callback.answer("Канал недоступен", show_alert=True)
            return
    if not isinstance(callback.message, Message):
        return
    await callback.answer()
    await _render_action(
        callback.message,
        channel,
        action,
        database,
        telegram_user_id=callback.from_user.id,
        requested_season_id=requested_season_id,
    )


async def _load_season(
    repository: SeasonRepository,
    channel_id: int,
    requested_season_id: int | None,
) -> Season | None:
    if requested_season_id is None:
        return await repository.get_active_by_channel_id(channel_id)
    season = await repository.get_by_id(requested_season_id)
    if (
        season is None
        or season.channel_id != channel_id
        or season.status not in {SeasonStatus.ACTIVE, SeasonStatus.FINISHED}
    ):
        return None
    return season


async def _render_action(
    message: Message,
    channel: Channel,
    action: str,
    database: Database,
    *,
    telegram_user_id: int | None,
    requested_season_id: int | None = None,
) -> None:
    async with database.session() as session:
        season = await _load_season(
            SeasonRepository(session),
            channel.id,
            requested_season_id,
        )
        if season is None:
            await message.answer("У канала нет выбранного активного или завершённого периода.")
            return
        rating = RatingService(session)
        if action == "me":
            if telegram_user_id is None:
                await message.answer("Не удалось определить пользователя.")
                return
            entry = await rating.get_user_entry(
                season,
                telegram_user_id,
                timezone=channel.timezone,
            )
            await message.answer(_format_personal(entry, season, channel))
            return
        order = {
            "comments": RatingOrder.COMMENTS,
            "reactions": RatingOrder.REACTIONS,
        }.get(action, RatingOrder.SCORE)
        page = await rating.get_page(season, timezone=channel.timezone, order=order)
    await message.answer(
        _format_page(page, season, channel, order),
        reply_markup=rating_keyboard(
            channel_id=channel.id,
            season_id=season.id,
            page=page.page,
            pages=max(math.ceil(page.total / page.page_size), 1),
            order=order,
        ),
    )


@router.callback_query(RatingCallback.filter())
async def rating_callback(
    callback: CallbackQuery,
    callback_data: RatingCallback,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    try:
        order = RatingOrder(callback_data.order)
    except ValueError:
        await callback.answer("Кнопка устарела", show_alert=True)
        return
    if callback_data.action not in {"page", "mine"}:
        await callback.answer("Кнопка устарела", show_alert=True)
        return
    async with database.session() as session:
        channel = await ChannelRepository(session).get_by_id(callback_data.channel_id)
        season = await SeasonRepository(session).get_by_id(callback_data.season_id)
        if (
            channel is None
            or season is None
            or season.channel_id != channel.id
            or season.status not in {SeasonStatus.ACTIVE, SeasonStatus.FINISHED}
        ):
            await callback.answer("Период больше не доступен", show_alert=True)
            return
        access = ChannelAccessService(bot, session, settings)
        if not await access.can_access(callback.from_user.id, channel, admin_only=False):
            await callback.answer("Канал недоступен", show_alert=True)
            return
        rating = RatingService(session)
        if callback_data.action == "mine":
            entry = await rating.get_user_entry(
                season,
                callback.from_user.id,
                timezone=channel.timezone,
            )
            await callback.answer()
            if isinstance(callback.message, Message):
                await callback.message.answer(_format_personal(entry, season, channel))
            return
        page = await rating.get_page(
            season,
            timezone=channel.timezone,
            page=callback_data.page,
            order=order,
        )
    if not isinstance(callback.message, Message):
        return
    await callback.answer("Обновлено" if callback_data.action == "page" else None)
    await callback.message.edit_text(
        _format_page(page, season, channel, order),
        reply_markup=rating_keyboard(
            channel_id=channel.id,
            season_id=season.id,
            page=page.page,
            pages=max(math.ceil(page.total / page.page_size), 1),
            order=order,
        ),
    )


def _format_page(
    page: RatingPage,
    season: Season,
    channel: Channel,
    order: RatingOrder,
) -> str:
    title = {
        RatingOrder.SCORE: "🏆 Рейтинг активности",
        RatingOrder.COMMENTS: "💬 Топ по комментариям",
        RatingOrder.REACTIONS: "👍 Топ по реакциям",
    }[order]
    lines = [
        f"<b>{title}</b>",
        f"Период: {escape(season.name)} · "
        f"{format_local_datetime(season.starts_at, channel.timezone)} — "
        f"{format_local_datetime(season.ends_at, channel.timezone)}",
        "",
    ]
    if not page.entries:
        lines.append("Активности пока нет.")
    for entry in page.entries:
        lines.extend(
            [
                f"{entry.position}. {escape(entry.display_name)} — {entry.score} баллов",
                f"   💬 {entry.counted_comments} · 👍 {entry.reactions}",
                "",
            ],
        )
    pages = max(math.ceil(page.total / page.page_size), 1)
    lines.append(f"Страница {page.page + 1}/{pages} · участников: {page.total}")
    return "\n".join(lines)


def _format_personal(
    entry: RatingEntry | None,
    season: Season,
    channel: Channel,
) -> str:
    if entry is None:
        return f"В периоде <b>{escape(season.name)}</b> у вас пока нет активности."
    return (
        f"<b>Личная статистика · {escape(season.name)}</b>\n"
        f"Место: {entry.position}\n"
        f"Баллы: {entry.score}\n"
        f"Комментарии: {entry.total_comments} фактических, "
        f"{entry.counted_comments} зачтённых\n"
        f"Реакции: {entry.reactions}\n"
        f"Активные дни: {entry.active_days}\n"
        f"Период: {format_local_datetime(season.starts_at, channel.timezone)} — "
        f"{format_local_datetime(season.ends_at, channel.timezone)}"
    )
