"""Comment repository."""

from datetime import datetime
from typing import cast

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.models.comment import Comment
from app.repositories.base import BaseRepository


class CommentRepository(BaseRepository[Comment]):
    """Persistence operations for discussion comments."""

    model: type[Comment] = Comment

    async def get_by_telegram_id(
        self,
        discussion_chat_id: int,
        telegram_message_id: int,
    ) -> Comment | None:
        statement = select(Comment).where(
            Comment.discussion_chat_id == discussion_chat_id,
            Comment.telegram_message_id == telegram_message_id,
        )
        return cast("Comment | None", await self.session.scalar(statement))

    async def get_by_telegram_id_for_channel(
        self,
        channel_id: int,
        telegram_message_id: int,
    ) -> Comment | None:
        """Resolve a reply target inside one configured discussion group."""
        statement = select(Comment).where(
            Comment.channel_id == channel_id,
            Comment.telegram_message_id == telegram_message_id,
        )
        return cast("Comment | None", await self.session.scalar(statement))

    async def telegram_id_exists(
        self,
        discussion_chat_id: int,
        telegram_message_id: int,
    ) -> bool:
        return await self.exists(
            Comment.discussion_chat_id == discussion_chat_id,
            Comment.telegram_message_id == telegram_message_id,
        )

    async def upsert_telegram_comment(
        self,
        *,
        channel_id: int,
        post_id: int,
        user_id: int,
        discussion_chat_id: int,
        telegram_message_id: int,
        reply_to_message_id: int | None,
        text_length: int,
        content_hash: str,
        created_at: datetime,
        is_countable: bool,
    ) -> tuple[Comment, bool]:
        """Insert a comment once and return whether this call created it."""
        values = {
            "channel_id": channel_id,
            "post_id": post_id,
            "user_id": user_id,
            "discussion_chat_id": discussion_chat_id,
            "telegram_message_id": telegram_message_id,
            "reply_to_message_id": reply_to_message_id,
            "text_length": text_length,
            "content_hash": content_hash,
            "created_at": created_at,
            "is_countable": is_countable,
        }
        statement = (
            insert(Comment)
            .values(**values)
            .on_conflict_do_nothing(constraint="uq_comments_discussion_message")
            .returning(Comment.id)
        )
        comment_id = await self.session.scalar(statement)
        created = comment_id is not None
        if comment_id is None:
            comment = await self.get_by_telegram_id(
                discussion_chat_id,
                telegram_message_id,
            )
        else:
            comment = await self.get_by_id(comment_id)
        if comment is None:  # pragma: no cover
            raise RuntimeError("persisted comment could not be loaded")
        return comment, created

    async def mark_deleted(self, discussion_chat_id: int, telegram_message_id: int) -> bool:
        """Administratively mark a known comment deleted; Bot API emits no delete update."""
        statement = (
            update(Comment)
            .where(
                Comment.discussion_chat_id == discussion_chat_id,
                Comment.telegram_message_id == telegram_message_id,
                Comment.deleted_at.is_(None),
            )
            .values(deleted_at=func.now(), is_countable=False)
            .returning(Comment.id)
        )
        return await self.session.scalar(statement) is not None
