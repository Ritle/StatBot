"""Integration tests for PostgreSQL-specific schema guarantees."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Channel,
    Comment,
    CurrentReaction,
    Post,
    ReactionEvent,
    Season,
    SeasonStatus,
    User,
)
from app.repositories import ChannelRepository, UserRepository

pytestmark = pytest.mark.integration


async def create_channel(
    session: AsyncSession,
    telegram_channel_id: int = -100_000_000_001,
    discussion_chat_id: int | None = -100_100_000_001,
) -> Channel:
    channel = Channel(
        telegram_channel_id=telegram_channel_id,
        title="Integration test channel",
        discussion_chat_id=discussion_chat_id,
    )
    session.add(channel)
    await session.flush()
    return channel


async def create_user(
    session: AsyncSession,
    telegram_user_id: int = 100_001,
) -> User:
    user = User(
        telegram_user_id=telegram_user_id,
        username="integration_user",
        first_name="Integration",
    )
    session.add(user)
    await session.flush()
    return user


async def create_post(
    session: AsyncSession,
    channel_id: int,
    telegram_message_id: int = 501,
) -> Post:
    post = Post(
        channel_id=channel_id,
        telegram_message_id=telegram_message_id,
        discussion_message_id=701,
        published_at=datetime.now(UTC),
    )
    session.add(post)
    await session.flush()
    return post


async def test_channel_creation_and_repository_lookup(
    db_session: AsyncSession,
) -> None:
    repository = ChannelRepository(db_session)
    channel = await repository.create(
        telegram_channel_id=-100_000_000_011,
        title="Created through repository",
    )

    loaded = await repository.get_by_telegram_id(channel.telegram_channel_id)

    assert loaded is channel
    assert channel.timezone == "Europe/Amsterdam"
    assert channel.is_active is True
    assert channel.created_at.tzinfo is not None
    assert channel.created_at.utcoffset() == timedelta(0)
    assert await repository.telegram_id_exists(channel.telegram_channel_id)
    updated = await repository.update(channel, title="Updated title")
    assert updated.title == "Updated title"
    assert await repository.get_by_id(channel.id) is channel


async def test_channel_telegram_id_is_unique(db_session: AsyncSession) -> None:
    await create_channel(db_session)
    db_session.add(
        Channel(
            telegram_channel_id=-100_000_000_001,
            title="Duplicate channel",
        ),
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_release_hardening_indexes_and_restrict_foreign_keys(
    db_session: AsyncSession,
) -> None:
    indexes = set(
        (
            await db_session.scalars(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE indexname IN "
                    "('ix_comments_channel_telegram_message', "
                    "'ix_current_reactions_channel_created_at')",
                ),
            )
        ).all(),
    )
    constraint_rows = (
        await db_session.execute(
            text(
                "SELECT tc.constraint_name, rc.delete_rule "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.referential_constraints rc "
                "ON rc.constraint_name = tc.constraint_name "
                "WHERE tc.constraint_name IN "
                "('fk_admin_audit_log_channel_id_channels', "
                "'fk_season_results_season_id_seasons')",
            ),
        )
    ).all()
    delete_rules: dict[str, str] = dict(
        (str(row[0]), str(row[1])) for row in constraint_rows
    )

    assert indexes == {
        "ix_comments_channel_telegram_message",
        "ix_current_reactions_channel_created_at",
    }
    assert delete_rules == {
        "fk_admin_audit_log_channel_id_channels": "RESTRICT",
        "fk_season_results_season_id_seasons": "RESTRICT",
    }


async def test_user_telegram_id_is_unique(db_session: AsyncSession) -> None:
    repository = UserRepository(db_session)
    await repository.create(
        telegram_user_id=100_001,
        first_name="First",
        is_bot=False,
    )
    db_session.add(
        User(
            telegram_user_id=100_001,
            first_name="Duplicate",
            is_bot=False,
        ),
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_only_one_active_season_per_channel(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    starts_at = datetime.now(UTC)
    db_session.add(
        Season(
            channel_id=channel.id,
            name="First active season",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=7),
            status=SeasonStatus.ACTIVE,
        ),
    )
    await db_session.flush()
    db_session.add(
        Season(
            channel_id=channel.id,
            name="Second active season",
            starts_at=starts_at,
            ends_at=starts_at + timedelta(days=14),
            status=SeasonStatus.ACTIVE,
        ),
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_active_seasons_are_allowed_for_different_channels(
    db_session: AsyncSession,
) -> None:
    first_channel = await create_channel(db_session)
    second_channel = await create_channel(
        db_session,
        telegram_channel_id=-100_000_000_002,
        discussion_chat_id=-100_100_000_002,
    )
    starts_at = datetime.now(UTC)
    db_session.add_all(
        [
            Season(
                channel_id=first_channel.id,
                name="First channel season",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(days=7),
                status=SeasonStatus.ACTIVE,
            ),
            Season(
                channel_id=second_channel.id,
                name="Second channel season",
                starts_at=starts_at,
                ends_at=starts_at + timedelta(days=7),
                status=SeasonStatus.ACTIVE,
            ),
        ],
    )

    await db_session.flush()


async def test_comment_telegram_identity_is_unique(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    user = await create_user(db_session)
    post = await create_post(db_session, channel.id)
    comment_values = {
        "channel_id": channel.id,
        "post_id": post.id,
        "user_id": user.id,
        "discussion_chat_id": channel.discussion_chat_id,
        "telegram_message_id": 900,
        "text_length": 12,
        "content_hash": "a" * 64,
    }
    db_session.add(Comment(**comment_values))
    await db_session.flush()
    db_session.add(Comment(**comment_values))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_current_reaction_identity_is_unique(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    user = await create_user(db_session)
    post = await create_post(db_session, channel.id)
    reaction_values = {
        "channel_id": channel.id,
        "post_id": post.id,
        "user_id": user.id,
        "reaction_key": "custom_emoji:5368324170671202286",
    }
    db_session.add(CurrentReaction(**reaction_values))
    await db_session.flush()
    db_session.add(CurrentReaction(**reaction_values))

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_reaction_event_uses_jsonb_and_update_id_is_idempotent(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    user = await create_user(db_session)
    post = await create_post(db_session, channel.id)
    event_values = {
        "channel_id": channel.id,
        "post_id": post.id,
        "user_id": user.id,
        "telegram_update_id": 700_001,
        "old_reactions": [{"type": "emoji", "emoji": "🔥"}],
        "new_reactions": [
            {
                "type": "custom_emoji",
                "custom_emoji_id": "5368324170671202286",
            },
        ],
    }
    event = ReactionEvent(**event_values)
    db_session.add(event)
    await db_session.flush()
    await db_session.refresh(event)

    assert event.new_reactions[0]["type"] == "custom_emoji"

    db_session.add(ReactionEvent(**event_values))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_foreign_keys_are_enforced(db_session: AsyncSession) -> None:
    db_session.add(
        Post(
            channel_id=999_999,
            telegram_message_id=1,
            published_at=datetime.now(UTC),
        ),
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_season_end_must_be_after_start(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    starts_at = datetime.now(UTC)
    db_session.add(
        Season(
            channel_id=channel.id,
            name="Invalid dates",
            starts_at=starts_at,
            ends_at=starts_at,
        ),
    )

    with pytest.raises(IntegrityError):
        await db_session.flush()
