"""Integration tests for exclusions, exports, audit and immutable rules."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import SeasonError
from app.models import AdminAuditLog, Channel, Comment, Post, Season, SeasonStatus, User
from app.services.audit import AdminAction, AuditService
from app.services.exclusions import ExclusionService
from app.services.export import ExportService
from app.services.seasons import SeasonService

pytestmark = pytest.mark.integration

START = datetime(2026, 8, 1, tzinfo=UTC)
END = datetime(2026, 9, 1, tzinfo=UTC)


async def seed_rating(
    session: AsyncSession,
    *,
    finished: bool = False,
) -> tuple[Channel, Season, User]:
    channel = Channel(
        telegram_channel_id=-100_800_001,
        discussion_chat_id=-100_800_002,
        title="Канал, «Тест»",
        timezone="Europe/Moscow",
    )
    user = User(
        telegram_user_id=8001,
        username="=2+3",
        first_name='Иван, "Тест"',
        last_name="Иванов",
        is_bot=False,
    )
    session.add_all([channel, user])
    await session.flush()
    post = Post(
        channel_id=channel.id,
        telegram_message_id=1,
        discussion_message_id=2,
        published_at=START,
    )
    season = Season(
        channel_id=channel.id,
        name="Август",
        starts_at=START,
        ends_at=END,
        status=SeasonStatus.ACTIVE,
        comment_points=2,
        reaction_points=1,
        minimum_comment_length=0,
    )
    session.add_all([post, season])
    await session.flush()
    session.add(
        Comment(
            channel_id=channel.id,
            post_id=post.id,
            user_id=user.id,
            discussion_chat_id=channel.discussion_chat_id,
            telegram_message_id=3,
            text_length=10,
            content_hash="a" * 64,
            created_at=START + timedelta(days=1),
        ),
    )
    await session.flush()
    if finished:
        season, _ = await SeasonService(session).finish(
            season.id,
            timezone=channel.timezone,
            finished_at=END + timedelta(seconds=1),
            actor_user_id=999,
        )
    return channel, season, user


async def test_exclude_by_id_unknown_username_and_include(db_session: AsyncSession) -> None:
    channel, _, user = await seed_rating(db_session)
    admin = User(telegram_user_id=999, first_name="Admin", is_bot=False)
    db_session.add(admin)
    await db_session.flush()
    service = ExclusionService(db_session)

    assert await service.find_known_users(str(user.telegram_user_id)) == [user]
    assert await service.find_known_users("@unknown") == []
    await service.exclude(
        channel_id=channel.id,
        user=user,
        admin_user=admin,
        telegram_admin_id=admin.telegram_user_id,
        reason="модерация",
    )
    assert await service.include(
        channel_id=channel.id,
        user=user,
        telegram_admin_id=admin.telegram_user_id,
    )


async def test_csv_has_bom_cyrillic_and_correct_escaping(db_session: AsyncSession) -> None:
    channel, season, _ = await seed_rating(db_session)
    artifact = await ExportService(db_session).create_csv(season, channel)
    try:
        payload = artifact.path.read_bytes()
        assert payload.startswith(b"\xef\xbb\xbf")
        decoded = payload.decode("utf-8-sig")
        assert '"Иван, ""Тест"""' in decoded
        rows = list(csv.reader(io.StringIO(decoded)))
        assert rows[1][2] == "'=2+3"
        assert rows[1][3] == 'Иван, "Тест"'
        assert artifact.filename.endswith("_20260801_20260901.csv")
    finally:
        await artifact.cleanup()
    assert not artifact.path.exists()


async def test_export_finished_period_uses_frozen_results(db_session: AsyncSession) -> None:
    channel, season, user = await seed_rating(db_session, finished=True)
    post = await db_session.scalar(select(Post).where(Post.channel_id == channel.id))
    assert post is not None
    db_session.add(
        Comment(
            channel_id=channel.id,
            post_id=post.id,
            user_id=user.id,
            discussion_chat_id=channel.discussion_chat_id,
            telegram_message_id=99,
            text_length=20,
            content_hash="b" * 64,
            created_at=START + timedelta(days=2),
        ),
    )
    await db_session.flush()

    artifact = await ExportService(db_session).create_csv(season, channel)
    try:
        rows = list(csv.reader(io.StringIO(artifact.path.read_text(encoding="utf-8-sig"))))
        assert rows[1][6] == "1"
    finally:
        await artifact.cleanup()


async def test_audit_action_is_persisted_without_secrets(db_session: AsyncSession) -> None:
    channel, _, _ = await seed_rating(db_session)
    await AuditService(db_session).record(
        admin_id=999,
        channel_id=channel.id,
        action=AdminAction.EXPORT,
        target_type="season",
        target_id=1,
        metadata={"rows": 1},
    )

    audit = await db_session.scalar(select(AdminAuditLog))

    assert audit is not None
    assert audit.action == "export"
    assert audit.metadata_json == {"rows": 1}
    assert "token" not in audit.metadata_json


async def test_finished_period_rules_cannot_change(db_session: AsyncSession) -> None:
    _, season, _ = await seed_rating(db_session, finished=True)

    with pytest.raises(SeasonError, match="завершённого"):
        await SeasonService(db_session).update_rules(
            season.id,
            actor_user_id=999,
            confirmed_active=True,
            comment_points=100,
        )

    assert await db_session.scalar(select(func.count()).select_from(AdminAuditLog)) == 1
