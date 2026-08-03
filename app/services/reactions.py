"""Idempotent ingestion of personal Telegram reaction updates."""

from __future__ import annotations

from aiogram.types import (
    MessageReactionUpdated,
    ReactionTypeCustomEmoji,
    ReactionTypeEmoji,
    ReactionTypeUnion,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import ChannelRepository, PostRepository, ReactionRepository, UserRepository


def reaction_key(reaction: ReactionTypeUnion) -> str:
    """Build a stable key for every Bot API reaction variant."""
    if isinstance(reaction, ReactionTypeEmoji):
        return f"emoji:{reaction.emoji}"
    if isinstance(reaction, ReactionTypeCustomEmoji):
        return f"custom_emoji:{reaction.custom_emoji_id}"
    return str(reaction.type)


class ReactionIngestService:
    """Persist an event log and synchronize its materialized active set."""

    def __init__(self, session: AsyncSession) -> None:
        self.channels = ChannelRepository(session)
        self.posts = PostRepository(session)
        self.users = UserRepository(session)
        self.reactions = ReactionRepository(session)

    async def ingest(self, event: MessageReactionUpdated, update_id: int) -> bool:
        sender = event.user
        if sender is None or sender.is_bot or event.actor_chat is not None:
            return False
        channel = await self.channels.get_by_telegram_id(event.chat.id)
        if channel is None or not channel.is_active:
            return False
        post = await self.posts.get_by_telegram_id(channel.id, event.message_id)
        if post is None:
            return False
        user = await self.users.upsert_telegram_user(
            telegram_user_id=sender.id,
            username=sender.username,
            first_name=sender.first_name,
            last_name=sender.last_name,
            is_bot=sender.is_bot,
        )
        new_keys = {reaction_key(item) for item in event.new_reaction}
        created = await self.reactions.record_event_once(
            channel_id=channel.id,
            post_id=post.id,
            user_id=user.id,
            telegram_update_id=update_id,
            old_reactions=[item.model_dump(mode="json") for item in event.old_reaction],
            new_reactions=[item.model_dump(mode="json") for item in event.new_reaction],
            created_at=event.date,
        )
        if not created:
            return False
        await self.reactions.synchronize_current_set(
            channel_id=channel.id,
            post_id=post.id,
            user_id=user.id,
            desired_keys=new_keys,
            created_at=event.date,
        )
        return True
