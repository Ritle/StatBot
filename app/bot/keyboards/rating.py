"""Inline keyboards for channel selection, lifecycle and pagination."""

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.callbacks import (
    ChannelChoiceCallback,
    CreateSeasonCallback,
    RatingCallback,
    SeasonActionCallback,
)
from app.models import Channel, Season
from app.schemas import RatingOrder


def channel_choice_keyboard(channels: list[Channel], action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels:
        builder.button(
            text=channel.title,
            callback_data=ChannelChoiceCallback(action=action, channel_id=channel.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def create_confirmation_keyboard(token: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Создать",
        callback_data=CreateSeasonCallback(token=token, accept=True),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=CreateSeasonCallback(token=token, accept=False),
    )
    return builder.as_markup()


def season_action_keyboard(seasons: list[Season], action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for season in seasons:
        builder.button(
            text=season.name,
            callback_data=SeasonActionCallback(action=action, season_id=season.id),
        )
    builder.adjust(1)
    return builder.as_markup()


def confirmation_keyboard(action: str, season_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Подтвердить",
        callback_data=SeasonActionCallback(action=action, season_id=season_id),
    )
    builder.button(
        text="❌ Не выполнять",
        callback_data=SeasonActionCallback(action="dismiss", season_id=season_id),
    )
    return builder.as_markup()


def rating_keyboard(
    *,
    channel_id: int,
    season_id: int,
    page: int,
    pages: int,
    order: RatingOrder,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if page > 0:
        builder.button(
            text="⬅️",
            callback_data=RatingCallback(
                action="page",
                channel_id=channel_id,
                season_id=season_id,
                page=page - 1,
                order=order.value,
            ),
        )
    if page + 1 < pages:
        builder.button(
            text="➡️",
            callback_data=RatingCallback(
                action="page",
                channel_id=channel_id,
                season_id=season_id,
                page=page + 1,
                order=order.value,
            ),
        )
    builder.button(
        text="🔄",
        callback_data=RatingCallback(
            action="page",
            channel_id=channel_id,
            season_id=season_id,
            page=page,
            order=order.value,
        ),
    )
    builder.button(
        text="👤 Моё место",
        callback_data=RatingCallback(
            action="mine",
            channel_id=channel_id,
            season_id=season_id,
            page=page,
            order=order.value,
        ),
    )
    builder.adjust(2, 2)
    return builder.as_markup()
