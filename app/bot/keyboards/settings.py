"""Administrative settings menu keyboards."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import ExclusionCallback, SettingsCallback
from app.models import Season, User


def settings_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = [
        ("🔌 Подключение канала", "connection"),
        ("📅 Текущий период", "period"),
        ("🗂 Список периодов", "seasons"),
        ("⚙️ Правила начисления", "rules"),
        ("🚫 Исключённые пользователи", "exclusions"),
        ("📤 Экспорт", "export"),
        ("🩺 Диагностика", "status"),
    ]
    for label, action in buttons:
        builder.button(
            text=label,
            callback_data=SettingsCallback(action=action, channel_id=channel_id),
        )
    builder.adjust(1)
    return builder.as_markup()


def settings_back_keyboard(channel_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="⬅️ В меню",
        callback_data=SettingsCallback(action="menu", channel_id=channel_id),
    )
    return builder.as_markup()


def period_choice_keyboard(
    channel_id: int,
    seasons: list[Season],
    action: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for season in seasons[:30]:
        builder.button(
            text=f"{season.name} · {season.status.value}",
            callback_data=SettingsCallback(
                action=action,
                channel_id=channel_id,
                object_id=season.id,
            ),
        )
    builder.button(
        text="⬅️ В меню",
        callback_data=SettingsCallback(action="menu", channel_id=channel_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def rules_keyboard(channel_id: int, season: Season) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if season.status.value in {"draft", "active"}:
        fields = [
            ("💬 Баллы за комментарий", "rule_comment"),
            ("👍 Баллы за реакцию", "rule_reaction"),
            ("📏 Минимальная длина", "rule_length"),
            ("📆 Дневной лимит", "rule_limit"),
        ]
        for label, action in fields:
            builder.button(
                text=label,
                callback_data=SettingsCallback(
                    action=action,
                    channel_id=channel_id,
                    object_id=season.id,
                ),
            )
    builder.button(
        text="⬅️ К периодам",
        callback_data=SettingsCallback(action="rules", channel_id=channel_id),
    )
    builder.adjust(1)
    return builder.as_markup()


def rule_confirmation_keyboard(
    channel_id: int,
    season_id: int,
    token: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Изменить активный период",
        callback_data=SettingsCallback(
            action="rule_apply",
            channel_id=channel_id,
            object_id=season_id,
            token=token,
        ),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=SettingsCallback(
            action="rule_cancel",
            channel_id=channel_id,
            object_id=season_id,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def exclusion_choice_keyboard(
    channel_id: int,
    users: list[User],
    action: str,
    token: str,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for user in users:
        label = f"{user.first_name} · {user.telegram_user_id}"
        if user.username:
            label += f" · @{user.username}"
        builder.button(
            text=label,
            callback_data=ExclusionCallback(
                action=action,
                channel_id=channel_id,
                user_id=user.id,
                token=token,
            ),
        )
    builder.button(
        text="❌ Отмена",
        callback_data=ExclusionCallback(
            action="cancel",
            channel_id=channel_id,
            user_id=0,
            token=token,
        ),
    )
    builder.adjust(1)
    return builder.as_markup()
