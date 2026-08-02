"""Callback payloads for administrative settings and exclusions."""

from aiogram.filters.callback_data import CallbackData


class SettingsCallback(CallbackData, prefix="set"):
    action: str
    channel_id: int
    object_id: int = 0
    token: str = "-"


class ExclusionCallback(CallbackData, prefix="exc"):
    action: str
    channel_id: int
    user_id: int
    token: str = "-"
