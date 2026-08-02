"""Integration coverage for transactional, idempotent comment persistence."""

from datetime import UTC, datetime

import pytest
from aiogram.enums import ChatType
from aiogram.types import Chat, Message, User
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Comment, Post
from app.models import User as StoredUser
from app.services.activity import ActivityService, IngestKind

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 3, 12, 0, tzinfo=UTC)
CHANNEL_ID = -100_000_000_101
DISCUSSION_ID = -100_100_000_101


def make_comment(message_id: int, username: str) -> Message:
    root = Message(
        message_id=701,
        date=NOW,
        chat=Chat(id=DISCUSSION_ID, type=ChatType.SUPERGROUP, title="Discussion"),
    )
    return Message(
        message_id=message_id,
        date=NOW,
        chat=Chat(id=DISCUSSION_ID, type=ChatType.SUPERGROUP, title="Discussion"),
        from_user=User(id=5001, is_bot=False, first_name="Ada", username=username),
        text="  Useful\n comment  ",
        reply_to_message=root,
    )


async def test_comment_is_saved_once_and_user_profile_is_refreshed(
    db_session: AsyncSession,
) -> None:
    channel = Channel(
        telegram_channel_id=CHANNEL_ID,
        discussion_chat_id=DISCUSSION_ID,
        title="Integration channel",
    )
    db_session.add(channel)
    await db_session.flush()
    post = Post(
        channel_id=channel.id,
        telegram_message_id=501,
        discussion_message_id=701,
        published_at=NOW,
    )
    db_session.add(post)
    await db_session.flush()
    service = ActivityService(db_session)

    first = await service.ingest_discussion_message(make_comment(901, "old_name"))
    repeated = await service.ingest_discussion_message(make_comment(901, "old_name"))
    second = await service.ingest_discussion_message(make_comment(902, "new_name"))

    assert first.kind is IngestKind.COMMENT and first.created
    assert repeated.kind is IngestKind.COMMENT and not repeated.created
    assert second.kind is IngestKind.COMMENT and second.created
    assert await db_session.scalar(select(func.count()).select_from(Comment)) == 2
    saved_comment = await db_session.scalar(
        select(Comment).where(Comment.telegram_message_id == 901),
    )
    assert saved_comment is not None
    assert saved_comment.text_length == len("Useful comment")
    assert len(saved_comment.content_hash) == 64
    saved_user = await db_session.scalar(
        select(StoredUser).where(StoredUser.telegram_user_id == 5001),
    )
    assert saved_user is not None
    assert saved_user.username == "new_name"
