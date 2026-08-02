"""Compact callback payloads for seasons and leaderboard navigation."""

from aiogram.filters.callback_data import CallbackData


class ChannelChoiceCallback(CallbackData, prefix="ch"):
    action: str
    channel_id: int


class CreateSeasonCallback(CallbackData, prefix="sc"):
    token: str
    accept: bool


class SeasonActionCallback(CallbackData, prefix="sa"):
    action: str
    season_id: int


class RatingCallback(CallbackData, prefix="rt"):
    action: str
    channel_id: int
    season_id: int
    page: int
    order: str
