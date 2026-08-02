"""Channel post model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, IdMixin


class Post(IdMixin, CreatedAtMixin, Base):
    """A channel publication linked to its discussion message."""

    __tablename__ = "posts"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "telegram_message_id",
            name="uq_posts_channel_telegram_message",
        ),
        Index(
            "ix_posts_channel_discussion_message",
            "channel_id",
            "discussion_message_id",
        ),
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discussion_message_id: Mapped[int | None] = mapped_column(BigInteger)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
