"""Discussion comment model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, IdMixin


class Comment(IdMixin, CreatedAtMixin, Base):
    """A user comment observed in a linked discussion chat."""

    __tablename__ = "comments"
    __table_args__ = (
        UniqueConstraint(
            "discussion_chat_id",
            "telegram_message_id",
            name="uq_comments_discussion_message",
        ),
        CheckConstraint(
            "text_length >= 0",
            name="text_length_non_negative",
        ),
        Index("ix_comments_channel_created_at", "channel_id", "created_at"),
        Index("ix_comments_user_created_at", "user_id", "created_at"),
        Index(
            "ix_comments_post_user_created_at",
            "post_id",
            "user_id",
            "created_at",
        ),
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    discussion_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reply_to_message_id: Mapped[int | None] = mapped_column(BigInteger)
    text_length: Mapped[int] = mapped_column(nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_countable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
