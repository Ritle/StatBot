"""Protected administrative menu, rule editing and CSV export."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.filters.state import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.admin_access import resolve_admin_channel, verify_admin_callback_channel
from app.bot.callbacks import ChannelChoiceCallback, SettingsCallback
from app.bot.keyboards import (
    period_choice_keyboard,
    rule_confirmation_keyboard,
    rules_keyboard,
    settings_back_keyboard,
    settings_keyboard,
)
from app.bot.presentation import format_status
from app.bot.states import RuleEditStates
from app.config import Settings
from app.database.session import Database
from app.exceptions import SeasonError, SetupError
from app.models import Channel, Season, SeasonStatus, User
from app.repositories import ChannelRepository, ExcludedUserRepository, SeasonRepository
from app.services.audit import AdminAction, AuditService
from app.services.channel_access import ChannelAccessService
from app.services.export import ExportService
from app.services.seasons import SeasonService
from app.services.status import ChannelStatusService
from app.utils.datetime import format_local_datetime

router = Router(name=__name__)
_RULE_TTL = timedelta(minutes=10)
_MAX_INTEGER_SETTING = 2_147_483_647
_RULE_FIELDS = {
    "rule_comment": "comment_points",
    "rule_reaction": "reaction_points",
    "rule_length": "minimum_comment_length",
    "rule_limit": "daily_comment_limit",
}


async def _show_menu(message: Message, channel: Channel, *, edit: bool = False) -> None:
    text = (
        f"<b>Настройки · {escape(channel.title)}</b>\n"
        "Выберите административный раздел. Права проверяются при каждом действии."
    )
    markup = settings_keyboard(channel.id)
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


@router.message(Command("settings"))
async def settings_command(
    message: Message,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await resolve_admin_channel(
        message,
        action="settings",
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is not None:
        await _show_menu(message, channel)


@router.callback_query(ChannelChoiceCallback.filter(F.action == "settings"))
async def settings_channel_selected(
    callback: CallbackQuery,
    callback_data: ChannelChoiceCallback,
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
    await _show_menu(callback.message, channel, edit=True)


@router.message(Command("export"))
async def export_command(
    message: Message,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    channel = await resolve_admin_channel(
        message,
        action="export",
        bot=bot,
        database=database,
        settings=settings,
    )
    if channel is not None:
        await _show_export_periods(message, channel, database)


@router.callback_query(ChannelChoiceCallback.filter(F.action == "export"))
async def export_channel_selected(
    callback: CallbackQuery,
    callback_data: ChannelChoiceCallback,
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
    await _show_export_periods(callback.message, channel, database)


@router.message(Command("cancel"), StateFilter(*RuleEditStates.__all_states__))
async def cancel_rule_edit(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Изменение правил отменено.")


@router.callback_query(SettingsCallback.filter())
async def settings_callback(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
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
    action = callback_data.action
    if action == "rule_apply":
        await _apply_confirmed_rule(callback, callback_data, state, channel, database)
        return
    if action == "rule_cancel":
        await state.clear()
        await callback.answer("Отменено")
        await _show_rules(callback.message, channel, callback_data.object_id, database)
        return
    if action == "menu":
        await state.clear()
        await callback.answer()
        await _show_menu(callback.message, channel, edit=True)
    elif action == "connection":
        await callback.answer()
        await callback.message.edit_text(
            "<b>Подключение канала</b>\n"
            f"Канал: {escape(channel.title)} (<code>{channel.telegram_channel_id}</code>)\n"
            f"Discussion group: <code>{channel.discussion_chat_id}</code>\n\n"
            "Для повторной проверки или изменения связи выполните /setup.",
            reply_markup=settings_back_keyboard(channel.id),
        )
    elif action in {"period", "seasons"}:
        await callback.answer()
        await _show_periods_section(
            callback.message,
            channel,
            database,
            active_only=action == "period",
        )
    elif action == "rules":
        await callback.answer()
        await _show_rule_periods(callback.message, channel, database)
    elif action == "rule_view":
        await callback.answer()
        await _show_rules(callback.message, channel, callback_data.object_id, database)
    elif action in _RULE_FIELDS:
        await _begin_rule_edit(
            callback,
            state,
            channel,
            callback_data.object_id,
            _RULE_FIELDS[action],
            database,
        )
    elif action == "exclusions":
        await callback.answer()
        await _show_exclusions(callback.message, channel, database)
    elif action == "export":
        await callback.answer()
        await _show_export_periods(callback.message, channel, database, edit=True)
    elif action == "export_period":
        await _perform_export(callback, channel, callback_data.object_id, database)
    elif action == "status":
        try:
            async with database.session() as session:
                status = await ChannelStatusService(bot, session, settings).get_status(
                    current_chat_id=channel.telegram_channel_id,
                    actor_user_id=callback.from_user.id,
                )
        except (SetupError, TelegramAPIError) as error:
            await callback.answer(f"Диагностика недоступна: {error}", show_alert=True)
            return
        await callback.answer()
        await callback.message.edit_text(
            format_status(status),
            reply_markup=settings_back_keyboard(channel.id),
        )
    else:
        await callback.answer("Кнопка устарела", show_alert=True)


async def _show_periods_section(
    message: Message,
    channel: Channel,
    database: Database,
    *,
    active_only: bool,
) -> None:
    async with database.session() as session:
        repository = SeasonRepository(session)
        seasons = (
            [season]
            if (season := await repository.get_active_by_channel_id(channel.id)) is not None
            else []
        ) if active_only else await repository.list_by_channel_id(channel.id)
    if not seasons:
        text = "Активного периода нет." if active_only else "Периодов пока нет."
    else:
        lines = ["<b>Текущий период</b>" if active_only else "<b>Периоды</b>"]
        for season in seasons[:20]:
            lines.append(
                f"• <code>{season.id}</code> · {escape(season.name)} · {season.status.value}\n"
                f"  {format_local_datetime(season.starts_at, channel.timezone)} — "
                f"{format_local_datetime(season.ends_at, channel.timezone)}",
            )
        text = "\n".join(lines)
    await message.edit_text(text, reply_markup=settings_back_keyboard(channel.id))


async def _show_rule_periods(message: Message, channel: Channel, database: Database) -> None:
    async with database.session() as session:
        seasons = await SeasonRepository(session).list_by_channel_id(channel.id)
    if not seasons:
        await message.edit_text(
            "Периодов пока нет.",
            reply_markup=settings_back_keyboard(channel.id),
        )
        return
    await message.edit_text(
        "Выберите период для просмотра правил:",
        reply_markup=period_choice_keyboard(channel.id, seasons, "rule_view"),
    )


async def _show_rules(
    message: Message,
    channel: Channel,
    season_id: int,
    database: Database,
) -> None:
    async with database.session() as session:
        season = await SeasonRepository(session).get_by_id(season_id)
    if season is None or season.channel_id != channel.id:
        await message.edit_text(
            "Период больше не доступен.",
            reply_markup=settings_back_keyboard(channel.id),
        )
        return
    limit = season.daily_comment_limit if season.daily_comment_limit is not None else "нет"
    warning = (
        "\n\n⚠️ Изменение активного периода потребует подтверждения."
        if season.status == SeasonStatus.ACTIVE
        else ""
    )
    if season.status == SeasonStatus.FINISHED:
        warning = "\n\n🔒 Завершённый результат зафиксирован; изменение запрещено."
    await message.edit_text(
        f"<b>Правила · {escape(season.name)}</b>\n"
        f"Статус: {season.status.value}\n"
        f"Баллы за комментарий: {season.comment_points}\n"
        f"Баллы за реакцию: {season.reaction_points}\n"
        f"Минимальная длина: {season.minimum_comment_length}\n"
        f"Дневной лимит: {limit}{warning}",
        reply_markup=rules_keyboard(channel.id, season),
    )


async def _begin_rule_edit(
    callback: CallbackQuery,
    state: FSMContext,
    channel: Channel,
    season_id: int,
    field: str,
    database: Database,
) -> None:
    async with database.session() as session:
        season = await SeasonRepository(session).get_by_id(season_id)
    if season is None or season.channel_id != channel.id:
        await callback.answer("Период не найден", show_alert=True)
        return
    if season.status not in {SeasonStatus.DRAFT, SeasonStatus.ACTIVE}:
        await callback.answer("Правила этого периода изменять нельзя", show_alert=True)
        return
    await state.set_state(RuleEditStates.value)
    await state.set_data(
        {
            "channel_id": channel.id,
            "season_id": season.id,
            "field": field,
            "expires_at": (datetime.now(UTC) + _RULE_TTL).isoformat(),
        },
    )
    prompt = (
        "Введите положительное число или «нет»."
        if field == "daily_comment_limit"
        else "Введите целое число 0 или больше."
    )
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(f"{prompt} Для отмены: /cancel.")


@router.message(RuleEditStates.value)
async def receive_rule_value(
    message: Message,
    state: FSMContext,
    bot: Bot,
    database: Database,
    settings: Settings,
) -> None:
    data = await state.get_data()
    if _fsm_expired(data):
        await state.clear()
        await message.answer("Сценарий изменения правил истёк. Откройте /settings заново.")
        return
    channel_id = int(data["channel_id"])
    async with database.session() as session:
        season = await SeasonRepository(session).get_by_id(int(data["season_id"]))
        stored_channel = await _load_channel(session, channel_id)
        if stored_channel is None:
            await state.clear()
            await message.answer("Канал больше не доступен.")
            return
        access = await _admin_allowed(bot, session, settings, message, stored_channel)
    if not access or season is None or season.channel_id != channel_id:
        await state.clear()
        await message.answer("Права или период изменились; операция отменена.")
        return
    field = str(data["field"])
    value = _parse_rule_value(field, message.text)
    if value is ...:
        await message.answer("Некорректное значение. Проверьте формат и повторите.")
        return
    if season.status == SeasonStatus.ACTIVE:
        token = secrets.token_hex(4)
        await state.update_data(value=value, token=token)
        await state.set_state(RuleEditStates.confirmation)
        await message.answer(
            "Изменение правил активного периода немедленно изменит текущий рейтинг. Подтвердить?",
            reply_markup=rule_confirmation_keyboard(channel_id, season.id, token),
        )
        return
    try:
        async with database.session() as session, session.begin():
            await _update_one_rule(
                SeasonService(session),
                season.id,
                field,
                value,
                message.from_user.id if message.from_user else 0,
                confirmed_active=False,
            )
    except SeasonError as error:
        await message.answer(f"Не удалось изменить правила: {escape(str(error))}")
        return
    await state.clear()
    await message.answer("Правило обновлено.")


async def _apply_confirmed_rule(
    callback: CallbackQuery,
    callback_data: SettingsCallback,
    state: FSMContext,
    channel: Channel,
    database: Database,
) -> None:
    data = await state.get_data()
    if (
        await state.get_state() != RuleEditStates.confirmation.state
        or _fsm_expired(data)
        or callback_data.token != data.get("token")
        or callback_data.object_id != int(data.get("season_id", 0))
        or channel.id != int(data.get("channel_id", 0))
    ):
        await state.clear()
        await callback.answer("Кнопка устарела", show_alert=True)
        return
    try:
        async with database.session() as session, session.begin():
            await _update_one_rule(
                SeasonService(session),
                callback_data.object_id,
                str(data["field"]),
                data.get("value"),
                callback.from_user.id,
                confirmed_active=True,
            )
    except SeasonError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    await callback.answer("Правило обновлено")
    if isinstance(callback.message, Message):
        await _show_rules(callback.message, channel, callback_data.object_id, database)


def _parse_rule_value(field: str, text: str | None) -> int | None | object:
    raw = (text or "").strip().casefold()
    if field == "daily_comment_limit" and raw in {"нет", "none", "0", "без лимита"}:
        return None
    try:
        value = int(raw)
    except ValueError:
        return ...
    if (
        value < 0
        or value > _MAX_INTEGER_SETTING
        or (field == "daily_comment_limit" and value == 0)
    ):
        return ...
    return value


async def _update_one_rule(
    service: SeasonService,
    season_id: int,
    field: str,
    value: object,
    admin_id: int,
    *,
    confirmed_active: bool,
) -> Season:
    def integer() -> int:
        if not isinstance(value, int):
            raise SeasonError("ожидалось целое число")
        return value

    if field == "comment_points":
        return await service.update_rules(
            season_id,
            actor_user_id=admin_id,
            confirmed_active=confirmed_active,
            comment_points=integer(),
        )
    if field == "reaction_points":
        return await service.update_rules(
            season_id,
            actor_user_id=admin_id,
            confirmed_active=confirmed_active,
            reaction_points=integer(),
        )
    if field == "minimum_comment_length":
        return await service.update_rules(
            season_id,
            actor_user_id=admin_id,
            confirmed_active=confirmed_active,
            minimum_comment_length=integer(),
        )
    if field == "daily_comment_limit":
        limit = integer() if value is not None else None
        return await service.update_rules(
            season_id,
            actor_user_id=admin_id,
            confirmed_active=confirmed_active,
            daily_comment_limit=limit,
        )
    raise SeasonError("неизвестное правило")


def _fsm_expired(data: dict[str, object]) -> bool:
    raw = data.get("expires_at")
    if raw is None:
        return True
    try:
        return datetime.fromisoformat(str(raw)) < datetime.now(UTC)
    except (TypeError, ValueError):
        return True


async def _load_channel(session: AsyncSession, channel_id: int) -> Channel | None:
    return await ChannelRepository(session).get_by_id(channel_id)


async def _admin_allowed(
    bot: Bot,
    session: AsyncSession,
    settings: Settings,
    message: Message,
    channel: Channel,
) -> bool:
    return message.from_user is not None and await ChannelAccessService(
        bot,
        session,
        settings,
    ).can_access(message.from_user.id, channel, admin_only=True)


async def _show_exclusions(message: Message, channel: Channel, database: Database) -> None:
    async with database.session() as session:
        exclusions = await ExcludedUserRepository(session).list_by_channel_id(channel.id)
        user_ids = [item.user_id for item in exclusions]
        users = (
            list((await session.scalars(select(User).where(User.id.in_(user_ids)))).all())
            if user_ids
            else []
        )
    profiles = {int(user.id): user for user in users}
    lines = ["<b>Исключённые пользователи</b>"]
    if not exclusions:
        lines.append("Список пуст.")
    for item in exclusions[:30]:
        user = profiles.get(item.user_id)
        if user is not None:
            lines.append(
                f"• {escape(str(user.first_name))} · <code>{user.telegram_user_id}</code>"
                f"{f' · @{escape(str(user.username))}' if user.username else ''}",
            )
    lines.append("\nУправление: /exclude и /include.")
    await message.edit_text("\n".join(lines), reply_markup=settings_back_keyboard(channel.id))


async def _show_export_periods(
    message: Message,
    channel: Channel,
    database: Database,
    *,
    edit: bool = False,
) -> None:
    async with database.session() as session:
        seasons = [
            season
            for season in await SeasonRepository(session).list_by_channel_id(channel.id)
            if season.status in {SeasonStatus.ACTIVE, SeasonStatus.FINISHED}
        ]
    if not seasons:
        text = "Нет активных или завершённых периодов для экспорта."
        markup = settings_back_keyboard(channel.id)
    else:
        text = "Выберите период для CSV-экспорта:"
        markup = period_choice_keyboard(channel.id, seasons, "export_period")
    if edit:
        await message.edit_text(text, reply_markup=markup)
    else:
        await message.answer(text, reply_markup=markup)


async def _perform_export(
    callback: CallbackQuery,
    channel: Channel,
    season_id: int,
    database: Database,
) -> None:
    async with database.session() as session:
        season = await SeasonRepository(session).get_by_id(season_id)
        if (
            season is None
            or season.channel_id != channel.id
            or season.status not in {SeasonStatus.ACTIVE, SeasonStatus.FINISHED}
        ):
            await callback.answer("Период больше не доступен", show_alert=True)
            return
        artifact = await ExportService(session).create_csv(season, channel)
    try:
        if not isinstance(callback.message, Message):
            return
        await callback.answer("Формирую CSV…")
        await callback.message.answer_document(
            FSInputFile(artifact.path, filename=artifact.filename),
            caption=f"Экспортировано строк: {artifact.row_count}",
        )
        async with database.session() as session, session.begin():
            await AuditService(session).record(
                admin_id=callback.from_user.id,
                channel_id=channel.id,
                action=AdminAction.EXPORT,
                target_type="season",
                target_id=season.id,
                metadata={"rows": artifact.row_count},
            )
    finally:
        await artifact.cleanup()
