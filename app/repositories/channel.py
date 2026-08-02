"""Channel repository."""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models.channel import Channel
from app.repositories.base import BaseRepository


class ChannelRepository(BaseRepository[Channel]):
    """Persistence operations for tracked channels."""

    model: type[Channel] = Channel

    async def get_by_telegram_id(self, telegram_channel_id: int) -> Channel | None:
        statement = select(Channel).where(
            Channel.telegram_channel_id == telegram_channel_id,
        )
        return cast("Channel | None", await self.session.scalar(statement))

    async def get_by_discussion_chat_id(self, discussion_chat_id: int) -> Channel | None:
        statement = select(Channel).where(
            Channel.discussion_chat_id == discussion_chat_id,
        )
        return cast("Channel | None", await self.session.scalar(statement))

    async def telegram_id_exists(self, telegram_channel_id: int) -> bool:
        return await self.exists(Channel.telegram_channel_id == telegram_channel_id)

    async def list_active(self) -> list[Channel]:
        statement = select(Channel).where(Channel.is_active.is_(True)).order_by(Channel.title)
        return list((await self.session.scalars(statement)).all())

    async def upsert_settings(
        self,
        *,
        telegram_channel_id: int,
        title: str,
        username: str | None,
        discussion_chat_id: int,
        timezone: str,
    ) -> Channel:
        """Create or refresh a channel configuration by stable Telegram ID."""
        statement = (
            insert(Channel)
            .values(
                telegram_channel_id=telegram_channel_id,
                title=title,
                username=username,
                discussion_chat_id=discussion_chat_id,
                timezone=timezone,
                is_active=True,
            )
            .on_conflict_do_update(
                index_elements=[Channel.telegram_channel_id],
                set_={
                    "title": title,
                    "username": username,
                    "discussion_chat_id": discussion_chat_id,
                    "timezone": timezone,
                    "is_active": True,
                    "updated_at": func.now(),
                },
            )
            .returning(Channel.id)
        )
        channel_id = await self.session.scalar(statement)
        if channel_id is None:  # pragma: no cover - PostgreSQL always returns the row
            raise RuntimeError("channel upsert did not return an identifier")
        channel = await self.get_by_id(channel_id)
        if channel is None:  # pragma: no cover - protected by the returning clause
            raise RuntimeError("upserted channel could not be loaded")
        await self.session.refresh(channel)
        return channel
