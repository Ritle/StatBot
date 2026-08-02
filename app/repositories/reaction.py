"""Reaction event and current-state repository."""

from datetime import datetime
from typing import Any, cast

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from app.models.reaction import CurrentReaction, ReactionEvent
from app.repositories.base import BaseRepository


class ReactionRepository(BaseRepository[ReactionEvent]):
    """Persistence operations for the event log and current reaction set."""

    model: type[ReactionEvent] = ReactionEvent

    async def get_by_telegram_id(self, telegram_update_id: int) -> ReactionEvent | None:
        statement = select(ReactionEvent).where(
            ReactionEvent.telegram_update_id == telegram_update_id,
        )
        return cast("ReactionEvent | None", await self.session.scalar(statement))

    async def telegram_id_exists(self, telegram_update_id: int) -> bool:
        return await self.exists(
            ReactionEvent.telegram_update_id == telegram_update_id,
        )

    async def get_current_by_id(self, reaction_id: int) -> CurrentReaction | None:
        return await self.session.get(CurrentReaction, reaction_id)

    async def get_current(
        self,
        channel_id: int,
        post_id: int,
        user_id: int,
        reaction_key: str,
    ) -> CurrentReaction | None:
        statement = select(CurrentReaction).where(
            CurrentReaction.channel_id == channel_id,
            CurrentReaction.post_id == post_id,
            CurrentReaction.user_id == user_id,
            CurrentReaction.reaction_key == reaction_key,
        )
        return cast("CurrentReaction | None", await self.session.scalar(statement))

    async def create_current(self, **values: Any) -> CurrentReaction:
        reaction = CurrentReaction(**values)
        return await self.save_current(reaction)

    async def save_current(self, reaction: CurrentReaction) -> CurrentReaction:
        self.session.add(reaction)
        await self.session.flush()
        await self.session.refresh(reaction)
        return reaction

    async def update_current(
        self,
        reaction: CurrentReaction,
        **values: Any,
    ) -> CurrentReaction:
        for field_name, value in values.items():
            if not hasattr(reaction, field_name):
                raise AttributeError(
                    f"CurrentReaction has no mapped field {field_name!r}",
                )
            setattr(reaction, field_name, value)
        return await self.save_current(reaction)

    async def current_exists(
        self,
        channel_id: int,
        post_id: int,
        user_id: int,
        reaction_key: str,
    ) -> bool:
        return await self.exists(
            CurrentReaction.channel_id == channel_id,
            CurrentReaction.post_id == post_id,
            CurrentReaction.user_id == user_id,
            CurrentReaction.reaction_key == reaction_key,
        )

    async def record_event_once(
        self,
        *,
        channel_id: int,
        post_id: int,
        user_id: int,
        telegram_update_id: int,
        old_reactions: list[dict[str, Any]],
        new_reactions: list[dict[str, Any]],
        created_at: datetime,
    ) -> bool:
        """Insert an immutable Telegram reaction update exactly once."""
        statement = (
            insert(ReactionEvent)
            .values(
                channel_id=channel_id,
                post_id=post_id,
                user_id=user_id,
                telegram_update_id=telegram_update_id,
                old_reactions=old_reactions,
                new_reactions=new_reactions,
                created_at=created_at,
            )
            .on_conflict_do_nothing(
                index_elements=[ReactionEvent.telegram_update_id],
                index_where=text("telegram_update_id IS NOT NULL"),
            )
            .returning(ReactionEvent.id)
        )
        return await self.session.scalar(statement) is not None

    async def apply_current_difference(
        self,
        *,
        channel_id: int,
        post_id: int,
        user_id: int,
        removed_keys: set[str],
        added_keys: set[str],
        created_at: datetime,
    ) -> None:
        """Apply set differences after the event log accepted an update."""
        if removed_keys:
            await self.session.execute(
                delete(CurrentReaction).where(
                    CurrentReaction.channel_id == channel_id,
                    CurrentReaction.post_id == post_id,
                    CurrentReaction.user_id == user_id,
                    CurrentReaction.reaction_key.in_(removed_keys),
                ),
            )
        if added_keys:
            statement = (
                insert(CurrentReaction)
                .values(
                    [
                        {
                            "channel_id": channel_id,
                            "post_id": post_id,
                            "user_id": user_id,
                            "reaction_key": key,
                            "created_at": created_at,
                            "updated_at": created_at,
                        }
                        for key in sorted(added_keys)
                    ],
                )
                .on_conflict_do_nothing(constraint="uq_current_reactions_actor_key")
            )
            await self.session.execute(statement)
