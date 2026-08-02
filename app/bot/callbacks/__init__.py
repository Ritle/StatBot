"""Telegram callback data definitions."""

from app.bot.callbacks.admin import ExclusionCallback, SettingsCallback
from app.bot.callbacks.rating import (
    ChannelChoiceCallback,
    CreateSeasonCallback,
    RatingCallback,
    SeasonActionCallback,
)

__all__ = [
    "ChannelChoiceCallback",
    "ExclusionCallback",
    "CreateSeasonCallback",
    "RatingCallback",
    "SeasonActionCallback",
    "SettingsCallback",
]
