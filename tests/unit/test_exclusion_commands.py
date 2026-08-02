"""Parsing tests for reply-based exclusions."""

from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User

from app.bot.handlers.exclusions import _command_payload


def test_exclusion_target_is_read_from_reply() -> None:
    chat = Chat(id=-1001, type=ChatType.SUPERGROUP, title="Group")
    target = User(id=77, is_bot=False, first_name="Target", username="known")
    replied = Message(message_id=1, date=datetime.now(UTC), chat=chat, from_user=target)
    command = Message(
        message_id=2,
        date=datetime.now(UTC),
        chat=chat,
        from_user=User(id=1, is_bot=False, first_name="Admin"),
        text="/exclude спам",
        reply_to_message=replied,
    )

    identifier, reason, reply_user = _command_payload(command)

    assert identifier is None
    assert reason == "спам"
    assert reply_user is not None and reply_user["telegram_user_id"] == 77


def test_exclusion_target_and_reason_are_parsed_from_arguments() -> None:
    command = Message(
        message_id=2,
        date=datetime.now(UTC),
        chat=Chat(id=-1001, type=ChatType.SUPERGROUP, title="Group"),
        from_user=User(id=1, is_bot=False, first_name="Admin"),
        text="/exclude 77 слишком, много сообщений",
    )

    assert _command_payload(command)[:2] == ("77", "слишком, много сообщений")
