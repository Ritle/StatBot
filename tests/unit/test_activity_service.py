"""Unit tests for comment-to-channel and comment-to-post resolution."""

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.activity import ActivityService, IngestKind

NOW = datetime(2026, 8, 3, tzinfo=UTC)


def make_comment(
    *,
    chat_id: int = -1002,
    message_id: int = 20,
    username: str | None = "before",
    reply_to_message_id: int = 11,
) -> Message:
    root = Message(
        message_id=reply_to_message_id,
        date=NOW,
        chat=Chat(id=chat_id, type=ChatType.SUPERGROUP, title="Discussion"),
    )
    return Message(
        message_id=message_id,
        date=NOW,
        chat=Chat(id=chat_id, type=ChatType.SUPERGROUP, title="Discussion"),
        from_user=User(
            id=7,
            is_bot=False,
            first_name="Ada",
            username=username,
        ),
        text="A useful reply",
        reply_to_message=root,
    )


def make_service() -> tuple[ActivityService, Any]:
    service = ActivityService(cast("AsyncSession", object()))
    mocks: Any = SimpleNamespace(
        channels=SimpleNamespace(get_by_discussion_chat_id=AsyncMock()),
        posts=SimpleNamespace(
            get_by_discussion_message_id=AsyncMock(),
            get_by_id=AsyncMock(),
        ),
        comments=SimpleNamespace(
            get_by_telegram_id_for_channel=AsyncMock(),
            upsert_telegram_comment=AsyncMock(),
        ),
        users=SimpleNamespace(upsert_telegram_user=AsyncMock()),
    )
    service.channels = cast(Any, mocks.channels)
    service.posts = cast(Any, mocks.posts)
    service.comments = cast(Any, mocks.comments)
    service.users = cast(Any, mocks.users)
    return service, mocks


async def test_unknown_discussion_group_is_ignored() -> None:
    service, mocks = make_service()
    mocks.channels.get_by_discussion_chat_id.return_value = None

    result = await service.ingest_discussion_message(make_comment())

    assert result.kind is IngestKind.IGNORED
    mocks.users.upsert_telegram_user.assert_not_awaited()


async def test_group_resolves_channel_and_direct_post() -> None:
    service, mocks = make_service()
    channel = SimpleNamespace(id=1, is_active=True, telegram_channel_id=-1001)
    post = SimpleNamespace(id=2)
    user = SimpleNamespace(id=3)
    mocks.channels.get_by_discussion_chat_id.return_value = channel
    mocks.posts.get_by_discussion_message_id.return_value = post
    mocks.users.upsert_telegram_user.return_value = user
    mocks.comments.upsert_telegram_comment.return_value = (SimpleNamespace(id=4), True)

    result = await service.ingest_discussion_message(make_comment())

    assert result.kind is IngestKind.COMMENT
    assert result.created is True
    mocks.posts.get_by_discussion_message_id.assert_awaited_once_with(1, 11)


async def test_comment_reply_inherits_parent_post() -> None:
    service, mocks = make_service()
    mocks.channels.get_by_discussion_chat_id.return_value = SimpleNamespace(
        id=1,
        is_active=True,
        telegram_channel_id=-1001,
    )
    mocks.posts.get_by_discussion_message_id.return_value = None
    mocks.comments.get_by_telegram_id_for_channel.return_value = SimpleNamespace(post_id=2)
    mocks.posts.get_by_id.return_value = SimpleNamespace(id=2)
    mocks.users.upsert_telegram_user.return_value = SimpleNamespace(id=3)
    mocks.comments.upsert_telegram_comment.return_value = (SimpleNamespace(id=4), True)

    result = await service.ingest_discussion_message(make_comment(reply_to_message_id=19))

    assert result.kind is IngestKind.COMMENT
    mocks.comments.get_by_telegram_id_for_channel.assert_awaited_once_with(1, 19)


async def test_repeated_delivery_uses_idempotent_repository_method() -> None:
    service, mocks = make_service()
    mocks.channels.get_by_discussion_chat_id.return_value = SimpleNamespace(
        id=1,
        is_active=True,
        telegram_channel_id=-1001,
    )
    mocks.posts.get_by_discussion_message_id.return_value = SimpleNamespace(id=2)
    mocks.users.upsert_telegram_user.return_value = SimpleNamespace(id=3)
    saved = SimpleNamespace(id=4)
    mocks.comments.upsert_telegram_comment.side_effect = [(saved, True), (saved, False)]
    message = make_comment()

    first = await service.ingest_discussion_message(message)
    second = await service.ingest_discussion_message(message)

    assert first.created is True
    assert second.created is False


async def test_latest_username_is_passed_to_user_upsert() -> None:
    service, mocks = make_service()
    mocks.channels.get_by_discussion_chat_id.return_value = SimpleNamespace(
        id=1,
        is_active=True,
        telegram_channel_id=-1001,
    )
    mocks.posts.get_by_discussion_message_id.return_value = SimpleNamespace(id=2)
    mocks.users.upsert_telegram_user.return_value = SimpleNamespace(id=3)
    mocks.comments.upsert_telegram_comment.return_value = (SimpleNamespace(id=4), True)

    await service.ingest_discussion_message(make_comment(username="after"))

    assert mocks.users.upsert_telegram_user.await_args.kwargs["username"] == "after"


async def test_comment_outside_linked_group_is_ignored() -> None:
    service, mocks = make_service()
    mocks.channels.get_by_discussion_chat_id.return_value = None

    result = await service.ingest_discussion_message(make_comment(chat_id=-9999))

    assert result.kind is IngestKind.IGNORED
