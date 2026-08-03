"""Integration tests for single-query rating calculation and final snapshots."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.enums import ChatType, ReactionTypeType
from aiogram.types import (
    Chat,
    MessageReactionUpdated,
    ReactionTypeEmoji,
)
from aiogram.types import User as TelegramUser
from sqlalchemy import event, func, select
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SeasonError
from app.models import (
    Channel,
    Comment,
    CurrentReaction,
    ExcludedUser,
    Post,
    Season,
    SeasonResult,
    SeasonStatus,
    User,
)
from app.repositories import SeasonRepository
from app.schemas import RatingOrder
from app.services.rating import RatingService
from app.services.reactions import ReactionIngestService
from app.services.seasons import SeasonService

pytestmark = pytest.mark.integration

CHANNEL_TELEGRAM_ID = -100_000_200_001
DISCUSSION_ID = -100_000_300_001
START = datetime(2026, 3, 28, 0, 0, tzinfo=UTC)
END = datetime(2026, 4, 2, 0, 0, tzinfo=UTC)


async def create_channel(session: AsyncSession, *, suffix: int = 1) -> Channel:
    channel = Channel(
        telegram_channel_id=CHANNEL_TELEGRAM_ID - suffix,
        discussion_chat_id=DISCUSSION_ID - suffix,
        title=f"Rating channel {suffix}",
        timezone="Europe/Amsterdam",
    )
    session.add(channel)
    await session.flush()
    return channel


async def create_season(
    session: AsyncSession,
    channel: Channel,
    **overrides: Any,
) -> Season:
    values: dict[str, Any] = {
        "channel_id": channel.id,
        "name": "Spring rating",
        "starts_at": START,
        "ends_at": END,
        "status": SeasonStatus.ACTIVE,
        "comment_points": 3,
        "reaction_points": 2,
        "daily_comment_limit": None,
        "minimum_comment_length": 0,
    }
    values.update(overrides)
    season = Season(**values)
    session.add(season)
    await session.flush()
    return season


async def create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    name: str | None = None,
) -> User:
    user = User(
        telegram_user_id=telegram_id,
        first_name=name or f"User {telegram_id}",
        is_bot=False,
    )
    session.add(user)
    await session.flush()
    return user


async def create_post(session: AsyncSession, channel: Channel, message_id: int = 10) -> Post:
    post = Post(
        channel_id=channel.id,
        telegram_message_id=message_id,
        discussion_message_id=message_id + 100,
        published_at=START,
    )
    session.add(post)
    await session.flush()
    return post


async def add_comment(
    session: AsyncSession,
    channel: Channel,
    post: Post,
    user: User,
    message_id: int,
    created_at: datetime,
    *,
    length: int = 20,
    is_countable: bool = True,
    deleted: bool = False,
) -> Comment:
    comment = Comment(
        channel_id=channel.id,
        post_id=post.id,
        user_id=user.id,
        discussion_chat_id=channel.discussion_chat_id,
        telegram_message_id=message_id,
        text_length=length,
        content_hash=f"{message_id:064x}",
        is_countable=is_countable,
        deleted_at=created_at if deleted else None,
        created_at=created_at,
    )
    session.add(comment)
    await session.flush()
    return comment


async def test_comment_boundaries_length_daily_limit_timezone_and_active_days(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    season = await create_season(
        db_session,
        channel,
        daily_comment_limit=1,
        minimum_comment_length=10,
    )
    user = await create_user(db_session, 100)
    post = await create_post(db_session, channel)
    await add_comment(db_session, channel, post, user, 1, START - timedelta(seconds=1))
    await add_comment(db_session, channel, post, user, 2, datetime(2026, 3, 28, 22, 30, tzinfo=UTC))
    await add_comment(db_session, channel, post, user, 3, datetime(2026, 3, 28, 22, 31, tzinfo=UTC))
    await add_comment(
        db_session,
        channel,
        post,
        user,
        4,
        datetime(2026, 3, 29, 8, 0, tzinfo=UTC),
        length=5,
    )
    await add_comment(db_session, channel, post, user, 5, datetime(2026, 3, 29, 22, 30, tzinfo=UTC))
    await add_comment(
        db_session,
        channel,
        post,
        user,
        6,
        datetime(2026, 3, 30, 8, 0, tzinfo=UTC),
        is_countable=False,
    )
    await add_comment(
        db_session,
        channel,
        post,
        user,
        7,
        datetime(2026, 3, 30, 9, 0, tzinfo=UTC),
        deleted=True,
    )
    await add_comment(db_session, channel, post, user, 8, END)

    page = await RatingService(db_session).get_page(
        season,
        timezone=channel.timezone,
    )

    assert len(page.entries) == 1
    entry = page.entries[0]
    assert entry.total_comments == 5
    assert entry.counted_comments == 2
    assert entry.active_days == 2
    assert entry.score == 6


async def test_excluded_users_other_channels_and_bots_do_not_participate(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session, suffix=1)
    other_channel = await create_channel(db_session, suffix=2)
    season = await create_season(db_session, channel)
    user = await create_user(db_session, 200)
    excluded = await create_user(db_session, 201)
    bot_user = User(telegram_user_id=202, first_name="Bot", is_bot=True)
    admin = await create_user(db_session, 999)
    db_session.add(bot_user)
    await db_session.flush()
    post = await create_post(db_session, channel, 20)
    other_post = await create_post(db_session, other_channel, 21)
    await add_comment(db_session, channel, post, user, 20, START + timedelta(hours=1))
    await add_comment(db_session, channel, post, excluded, 21, START + timedelta(hours=1))
    await add_comment(db_session, channel, post, bot_user, 22, START + timedelta(hours=1))
    await add_comment(
        db_session,
        other_channel,
        other_post,
        user,
        23,
        START + timedelta(hours=1),
    )
    db_session.add(
        ExcludedUser(channel_id=channel.id, user_id=excluded.id, created_by=admin.id),
    )
    await db_session.flush()

    page = await RatingService(db_session).get_page(season, timezone=channel.timezone)

    assert [entry.telegram_user_id for entry in page.entries] == [200]


async def test_reactions_inside_period_are_active_and_preperiod_reactions_are_not(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    season = await create_season(db_session, channel)
    user = await create_user(db_session, 300)
    post = await create_post(db_session, channel)
    db_session.add_all(
        [
            CurrentReaction(
                channel_id=channel.id,
                post_id=post.id,
                user_id=user.id,
                reaction_key="emoji:🔥",
                created_at=START + timedelta(hours=1),
            ),
            CurrentReaction(
                channel_id=channel.id,
                post_id=post.id,
                user_id=user.id,
                reaction_key="emoji:👍",
                created_at=START - timedelta(hours=1),
            ),
        ],
    )
    await db_session.flush()

    entry = (await RatingService(db_session).get_page(season, timezone=channel.timezone)).entries[0]

    assert entry.reactions == 1
    assert entry.score == 2


async def test_reaction_ingestion_is_idempotent_and_removal_updates_current_set(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    user = TelegramUser(id=400, is_bot=False, first_name="Reaction user")
    await create_post(db_session, channel, message_id=77)
    chat = Chat(id=channel.telegram_channel_id, type=ChatType.CHANNEL, title="Channel")
    added = MessageReactionUpdated(
        chat=chat,
        message_id=77,
        date=START + timedelta(hours=1),
        old_reaction=[],
        new_reaction=[ReactionTypeEmoji(type=ReactionTypeType.EMOJI, emoji="🔥")],
        user=user,
    )
    removed = MessageReactionUpdated(
        chat=chat,
        message_id=77,
        date=START + timedelta(hours=2),
        old_reaction=[ReactionTypeEmoji(type=ReactionTypeType.EMOJI, emoji="🔥")],
        new_reaction=[],
        user=user,
    )
    service = ReactionIngestService(db_session)

    assert await service.ingest(added, 9001) is True
    assert await service.ingest(added, 9001) is False
    assert await db_session.scalar(select(func.count()).select_from(CurrentReaction)) == 1
    assert await service.ingest(removed, 9002) is True
    assert await db_session.scalar(select(func.count()).select_from(CurrentReaction)) == 0


async def test_reaction_snapshot_removes_stale_materialized_keys(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    stored_user = await create_user(db_session, 401)
    post = await create_post(db_session, channel, message_id=78)
    db_session.add(
        CurrentReaction(
            channel_id=channel.id,
            post_id=post.id,
            user_id=stored_user.id,
            reaction_key="emoji:🔥",
            created_at=START,
        ),
    )
    await db_session.flush()
    event = MessageReactionUpdated(
        chat=Chat(id=channel.telegram_channel_id, type=ChatType.CHANNEL, title="Channel"),
        message_id=post.telegram_message_id,
        date=START + timedelta(hours=1),
        old_reaction=[],
        new_reaction=[ReactionTypeEmoji(type=ReactionTypeType.EMOJI, emoji="👍")],
        user=TelegramUser(id=401, is_bot=False, first_name="Reaction user"),
    )

    assert await ReactionIngestService(db_session).ingest(event, 9003) is True
    keys = list(await db_session.scalars(select(CurrentReaction.reaction_key)))
    assert keys == ["emoji:👍"]


async def test_equal_scores_use_deterministic_telegram_id_tiebreak(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    season = await create_season(db_session, channel)
    post = await create_post(db_session, channel)
    higher_id = await create_user(db_session, 502)
    lower_id = await create_user(db_session, 501)
    await add_comment(db_session, channel, post, higher_id, 31, START + timedelta(hours=1))
    await add_comment(db_session, channel, post, lower_id, 32, START + timedelta(hours=1))

    page = await RatingService(db_session).get_page(season, timezone=channel.timezone)

    assert [entry.telegram_user_id for entry in page.entries] == [501, 502]
    assert [entry.position for entry in page.entries] == [1, 2]


async def test_pagination_personal_position_and_comment_sorting(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    season = await create_season(db_session, channel, comment_points=1)
    post = await create_post(db_session, channel)
    for index in range(12):
        user = await create_user(db_session, 600 + index)
        for comment_index in range(index + 1):
            await add_comment(
                db_session,
                channel,
                post,
                user,
                1000 + index * 20 + comment_index,
                START + timedelta(hours=index, minutes=comment_index),
            )
    service = RatingService(db_session)

    second_page = await service.get_page(
        season,
        timezone=channel.timezone,
        page=1,
        page_size=10,
        order=RatingOrder.COMMENTS,
    )
    personal = await service.get_user_entry(season, 600, timezone=channel.timezone)

    assert second_page.total == 12
    assert len(second_page.entries) == 2
    assert personal is not None and personal.position == 12


async def test_out_of_range_page_falls_back_to_first_page(db_session: AsyncSession) -> None:
    channel = await create_channel(db_session)
    season = await create_season(db_session, channel)
    user = await create_user(db_session, 699)
    post = await create_post(db_session, channel)
    await add_comment(db_session, channel, post, user, 991, START + timedelta(hours=1))

    page = await RatingService(db_session).get_page(
        season,
        timezone=channel.timezone,
        page=999,
    )

    assert page.page == 0
    assert page.total == 1
    assert page.entries[0].telegram_user_id == 699


async def test_finish_freezes_results_against_later_activity(
    db_session: AsyncSession,
) -> None:
    channel = await create_channel(db_session)
    season = await create_season(db_session, channel)
    user = await create_user(db_session, 700)
    post = await create_post(db_session, channel)
    await add_comment(db_session, channel, post, user, 80, START + timedelta(hours=1))
    service = SeasonService(db_session)

    finished, entries = await service.finish(
        season.id,
        timezone=channel.timezone,
        finished_at=END + timedelta(hours=1),
    )
    await add_comment(db_session, channel, post, user, 81, START + timedelta(hours=2))
    frozen = await RatingService(db_session).get_page(finished, timezone=channel.timezone)

    assert finished.status == SeasonStatus.FINISHED
    assert len(entries) == 1
    assert frozen.entries[0].counted_comments == 1
    assert await db_session.scalar(select(func.count()).select_from(SeasonResult)) == 1
    with pytest.raises(SeasonError, match="нет активного периода"):
        await service.recalculate_active(channel.id, timezone=channel.timezone)


async def test_rating_page_executes_one_aggregation_query(db_session: AsyncSession) -> None:
    channel = await create_channel(db_session)
    season = await create_season(db_session, channel)
    user = await create_user(db_session, 800)
    post = await create_post(db_session, channel)
    await add_comment(db_session, channel, post, user, 90, START + timedelta(hours=1))
    bind = db_session.sync_session.get_bind()
    statements: list[str] = []

    def count_statement(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        statements.append(statement)

    event.listen(bind, "before_cursor_execute", count_statement)
    try:
        await RatingService(db_session).get_page(season, timezone=channel.timezone)
    finally:
        event.remove(bind, "before_cursor_execute", count_statement)

    assert len(statements) == 1


async def test_absence_of_active_period_is_channel_specific(db_session: AsyncSession) -> None:
    first = await create_channel(db_session, suffix=1)
    second = await create_channel(db_session, suffix=2)
    await create_season(db_session, first)
    repository = SeasonRepository(db_session)

    assert await repository.get_active_by_channel_id(first.id) is not None
    assert await repository.get_active_by_channel_id(second.id) is None
