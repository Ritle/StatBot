"""Internal, transport-independent representations of Telegram updates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TelegramUserData:
    """Telegram user fields persisted by the application."""

    telegram_user_id: int
    username: str | None
    first_name: str
    last_name: str | None
    is_bot: bool


@dataclass(frozen=True, slots=True)
class TelegramPostData:
    """A channel publication, optionally observed through its discussion copy."""

    channel_chat_id: int
    message_id: int
    published_at: datetime
    discussion_message_id: int | None = None


@dataclass(frozen=True, slots=True)
class TelegramCommentData:
    """A supported personal message from a discussion group."""

    discussion_chat_id: int
    message_id: int
    created_at: datetime
    reply_to_message_id: int | None
    message_thread_id: int | None
    text_length: int
    content_hash: str
    user: TelegramUserData
