"""Idempotent publication and discussion-comment ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Post
from app.repositories import ChannelRepository, CommentRepository, PostRepository, UserRepository
from app.services.telegram_mapper import map_automatic_forward, map_channel_post, map_comment


class IngestKind(StrEnum):
    IGNORED = "ignored"
    POST = "post"
    COMMENT = "comment"


@dataclass(frozen=True, slots=True)
class IngestResult:
    kind: IngestKind
    created: bool = False


class ActivityService:
    """Resolve Telegram relationships while repositories own persistence details."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.channels = ChannelRepository(session)
        self.posts = PostRepository(session)
        self.comments = CommentRepository(session)
        self.users = UserRepository(session)

    async def ingest_channel_post(self, message: Message) -> IngestResult:
        data = map_channel_post(message)
        if data is None:
            return IngestResult(IngestKind.IGNORED)
        channel = await self.channels.get_by_telegram_id(data.channel_chat_id)
        if channel is None or not channel.is_active:
            return IngestResult(IngestKind.IGNORED)
        existing = await self.posts.get_by_telegram_id(channel.id, data.message_id)
        await self.posts.upsert_telegram_post(
            channel_id=channel.id,
            telegram_message_id=data.message_id,
            published_at=data.published_at,
            discussion_message_id=data.discussion_message_id,
        )
        return IngestResult(IngestKind.POST, created=existing is None)

    async def ingest_discussion_message(self, message: Message) -> IngestResult:
        channel = await self.channels.get_by_discussion_chat_id(message.chat.id)
        if channel is None or not channel.is_active:
            return IngestResult(IngestKind.IGNORED)

        forwarded_post = map_automatic_forward(message)
        if forwarded_post is not None:
            if forwarded_post.channel_chat_id != channel.telegram_channel_id:
                return IngestResult(IngestKind.IGNORED)
            existing = await self.posts.get_by_telegram_id(channel.id, forwarded_post.message_id)
            await self.posts.upsert_telegram_post(
                channel_id=channel.id,
                telegram_message_id=forwarded_post.message_id,
                published_at=forwarded_post.published_at,
                discussion_message_id=forwarded_post.discussion_message_id,
            )
            return IngestResult(IngestKind.POST, created=existing is None)

        data = map_comment(message)
        if data is None:
            return IngestResult(IngestKind.IGNORED)
        post = await self._resolve_post(
            channel.id,
            data.reply_to_message_id,
            data.message_thread_id,
        )
        if post is None:
            return IngestResult(IngestKind.IGNORED)

        user = await self.users.upsert_telegram_user(
            telegram_user_id=data.user.telegram_user_id,
            username=data.user.username,
            first_name=data.user.first_name,
            last_name=data.user.last_name,
            is_bot=data.user.is_bot,
        )
        _, created = await self.comments.upsert_telegram_comment(
            channel_id=channel.id,
            post_id=post.id,
            user_id=user.id,
            discussion_chat_id=data.discussion_chat_id,
            telegram_message_id=data.message_id,
            reply_to_message_id=data.reply_to_message_id,
            text_length=data.text_length,
            content_hash=data.content_hash,
            created_at=data.created_at,
            is_countable=True,
        )
        return IngestResult(IngestKind.COMMENT, created=created)

    async def mark_comment_deleted(
        self,
        discussion_chat_id: int,
        telegram_message_id: int,
    ) -> bool:
        """Support an authenticated administrative flow that confirms a deletion."""
        return await self.comments.mark_deleted(discussion_chat_id, telegram_message_id)

    async def _resolve_post(
        self,
        channel_id: int,
        reply_to_message_id: int | None,
        message_thread_id: int | None,
    ) -> Post | None:
        for target_message_id in (reply_to_message_id, message_thread_id):
            if target_message_id is None:
                continue
            post = await self.posts.get_by_discussion_message_id(channel_id, target_message_id)
            if post is not None:
                return post
            parent = await self.comments.get_by_telegram_id_for_channel(
                channel_id,
                target_message_id,
            )
            if parent is not None:
                return await self.posts.get_by_id(parent.post_id)
        return None
