"""Reaction event and current-state repository."""

from typing import Any, cast

from sqlalchemy import select

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
