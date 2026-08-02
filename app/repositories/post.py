"""Post repository."""

from datetime import datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.models.post import Post
from app.repositories.base import BaseRepository


class PostRepository(BaseRepository[Post]):
    """Persistence operations for channel publications."""

    model: type[Post] = Post

    async def get_by_telegram_id(
        self,
        channel_id: int,
        telegram_message_id: int,
    ) -> Post | None:
        statement = select(Post).where(
            Post.channel_id == channel_id,
            Post.telegram_message_id == telegram_message_id,
        )
        return cast("Post | None", await self.session.scalar(statement))

    async def telegram_id_exists(
        self,
        channel_id: int,
        telegram_message_id: int,
    ) -> bool:
        return await self.exists(
            Post.channel_id == channel_id,
            Post.telegram_message_id == telegram_message_id,
        )

    async def get_by_discussion_message_id(
        self,
        channel_id: int,
        discussion_message_id: int,
    ) -> Post | None:
        statement = select(Post).where(
            Post.channel_id == channel_id,
            Post.discussion_message_id == discussion_message_id,
        )
        return cast("Post | None", await self.session.scalar(statement))

    async def upsert_telegram_post(
        self,
        *,
        channel_id: int,
        telegram_message_id: int,
        published_at: datetime,
        discussion_message_id: int | None,
    ) -> Post:
        """Idempotently store a post and enrich its discussion identity when known."""
        values = {
            "channel_id": channel_id,
            "telegram_message_id": telegram_message_id,
            "published_at": published_at,
            "discussion_message_id": discussion_message_id,
        }
        update_values: dict[str, object] = {"published_at": published_at}
        if discussion_message_id is not None:
            update_values["discussion_message_id"] = discussion_message_id
        statement = (
            insert(Post)
            .values(**values)
            .on_conflict_do_update(
                constraint="uq_posts_channel_telegram_message",
                set_=update_values,
            )
            .returning(Post.id)
        )
        post_id = await self.session.scalar(statement)
        if post_id is None:  # pragma: no cover
            raise RuntimeError("post upsert did not return an identifier")
        post = await self.get_by_id(post_id)
        if post is None:  # pragma: no cover
            raise RuntimeError("upserted post could not be loaded")
        await self.session.refresh(post)
        return post
