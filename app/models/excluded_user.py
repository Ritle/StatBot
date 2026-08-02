"""Per-channel excluded user model."""

from __future__ import annotations

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, IdMixin


class ExcludedUser(IdMixin, CreatedAtMixin, Base):
    """A user excluded from a channel's activity calculations."""

    __tablename__ = "excluded_users"
    __table_args__ = (
        UniqueConstraint(
            "channel_id",
            "user_id",
            name="uq_excluded_users_channel_user",
        ),
        Index("ix_excluded_users_user_id", "user_id"),
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    reason: Mapped[str | None] = mapped_column(String(500))
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
