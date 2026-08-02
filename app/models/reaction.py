"""Reaction event log and materialized current reaction state."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, IdMixin, TimestampMixin


class ReactionEvent(IdMixin, CreatedAtMixin, Base):
    """Immutable before/after snapshot received from Telegram."""

    __tablename__ = "reaction_events"
    __table_args__ = (
        Index(
            "uq_reaction_events_telegram_update_id",
            "telegram_update_id",
            unique=True,
            postgresql_where=text("telegram_update_id IS NOT NULL"),
        ),
        Index(
            "ix_reaction_events_channel_created_at",
            "channel_id",
            "created_at",
        ),
        Index(
            "ix_reaction_events_post_user_created_at",
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
    telegram_update_id: Mapped[int | None] = mapped_column(BigInteger)
    old_reactions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    new_reactions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )


class CurrentReaction(IdMixin, TimestampMixin, Base):
    """One reaction currently set by one user on one post."""

    __tablename__ = "current_reactions"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "post_id",
            "user_id",
            "reaction_key",
            name="uq_current_reactions_actor_key",
        ),
        Index("ix_current_reactions_post_user", "post_id", "user_id"),
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
    reaction_key: Mapped[str] = mapped_column(String(512), nullable=False)
