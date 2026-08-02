"""Unit tests for Telegram-to-domain mapping decisions."""

from datetime import UTC, datetime

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, PhotoSize, User

from app.services.telegram_mapper import map_comment

NOW = datetime(2026, 8, 3, tzinfo=UTC)


def make_message(**values: object) -> Message:
    defaults: dict[str, object] = {
        "message_id": 10,
        "date": NOW,
        "chat": Chat(id=-1001, type=ChatType.SUPERGROUP, title="Discussion"),
        "from_user": User(id=7, is_bot=False, first_name="Ada", username="ada"),
        "text": "hello",
    }
    defaults.update(values)
    return Message(**defaults)  # type: ignore[arg-type]


def test_bot_message_is_ignored() -> None:
    message = make_message(
        from_user=User(id=8, is_bot=True, first_name="Other bot"),
    )

    assert map_comment(message) is None


def test_service_message_is_ignored() -> None:
    member = User(id=9, is_bot=False, first_name="New")
    message = make_message(text=None, new_chat_members=[member])

    assert map_comment(message) is None


def test_media_without_caption_is_mapped_with_zero_length() -> None:
    photo = PhotoSize(file_id="file", file_unique_id="unique", width=1, height=1)
    message = make_message(text=None, photo=[photo])

    mapped = map_comment(message)

    assert mapped is not None
    assert mapped.text_length == 0


def test_anonymous_sender_chat_is_not_a_personal_comment() -> None:
    message = make_message(
        sender_chat=Chat(id=-2002, type=ChatType.CHANNEL, title="Channel"),
    )

    assert map_comment(message) is None
