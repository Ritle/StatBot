"""Map aiogram models into small internal structures."""

from __future__ import annotations

from aiogram.enums import ContentType
from aiogram.types import Message, MessageOriginChannel

from app.schemas.telegram import TelegramCommentData, TelegramPostData, TelegramUserData
from app.utils.content import content_fingerprint

_SUPPORTED_COMMENT_TYPES = frozenset(
    {
        ContentType.TEXT,
        ContentType.ANIMATION,
        ContentType.AUDIO,
        ContentType.CONTACT,
        ContentType.DICE,
        ContentType.DOCUMENT,
        ContentType.GAME,
        ContentType.LOCATION,
        ContentType.PAID_MEDIA,
        ContentType.PHOTO,
        ContentType.POLL,
        ContentType.STICKER,
        ContentType.STORY,
        ContentType.VENUE,
        ContentType.VIDEO,
        ContentType.VIDEO_NOTE,
        ContentType.VOICE,
    },
)


def map_channel_post(message: Message) -> TelegramPostData | None:
    """Map a genuine channel post and reject messages from other chat types."""
    if message.chat.type != "channel":
        return None
    return TelegramPostData(
        channel_chat_id=message.chat.id,
        message_id=message.message_id,
        published_at=message.date,
    )


def map_automatic_forward(message: Message) -> TelegramPostData | None:
    """Map Telegram's automatic discussion copy of a channel publication."""
    origin = message.forward_origin
    if not message.is_automatic_forward or not isinstance(origin, MessageOriginChannel):
        return None
    return TelegramPostData(
        channel_chat_id=origin.chat.id,
        message_id=origin.message_id,
        published_at=origin.date,
        discussion_message_id=message.message_id,
    )


def map_comment(message: Message) -> TelegramCommentData | None:
    """Map a countable personal message, excluding bots, service and anonymous senders."""
    sender = message.from_user
    if (
        message.chat.type not in {"group", "supergroup"}
        or message.content_type not in _SUPPORTED_COMMENT_TYPES
        or sender is None
        or sender.is_bot
        or message.sender_chat is not None
    ):
        return None

    text_length, content_hash = content_fingerprint(message.text, message.caption)
    return TelegramCommentData(
        discussion_chat_id=message.chat.id,
        message_id=message.message_id,
        created_at=message.date,
        reply_to_message_id=(
            message.reply_to_message.message_id if message.reply_to_message is not None else None
        ),
        message_thread_id=message.message_thread_id,
        text_length=text_length,
        content_hash=content_hash,
        user=TelegramUserData(
            telegram_user_id=sender.id,
            username=sender.username,
            first_name=sender.first_name,
            last_name=sender.last_name,
            is_bot=sender.is_bot,
        ),
    )
