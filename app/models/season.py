"""Rating season model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, IdMixin, TimestampMixin
from app.models.enums import SeasonStatus


def _season_status_values(enum_class: type[SeasonStatus]) -> list[str]:
    return [status.value for status in enum_class]


season_status_type = Enum(
    SeasonStatus,
    name="season_status",
    values_callable=_season_status_values,
    validate_strings=True,
)


class Season(IdMixin, TimestampMixin, Base):
    """A bounded period with immutable-at-finish scoring settings."""

    __tablename__ = "seasons"
    __table_args__ = (
        CheckConstraint("ends_at > starts_at", name="valid_date_range"),
        CheckConstraint("comment_points >= 0", name="comment_points_non_negative"),
        CheckConstraint("reaction_points >= 0", name="reaction_points_non_negative"),
        CheckConstraint(
            "minimum_comment_length >= 0",
            name="minimum_comment_length_non_negative",
        ),
        CheckConstraint(
            "daily_comment_limit IS NULL OR daily_comment_limit > 0",
            name="daily_comment_limit_positive",
        ),
        Index("ix_seasons_channel_status", "channel_id", "status"),
        Index("ix_seasons_status_date_range", "status", "starts_at", "ends_at"),
        Index(
            "uq_seasons_one_active_per_channel",
            "channel_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    status: Mapped[SeasonStatus] = mapped_column(
        season_status_type,
        default=SeasonStatus.DRAFT,
        server_default=text("'draft'"),
        nullable=False,
    )
    comment_points: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    reaction_points: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    daily_comment_limit: Mapped[int | None]
    minimum_comment_length: Mapped[int] = mapped_column(
        default=0,
        server_default=text("0"),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
