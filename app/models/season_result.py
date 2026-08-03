"""Finalized rating result model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, IdMixin


class SeasonResult(IdMixin, CreatedAtMixin, Base):
    """A persisted user result for a finished season."""

    __tablename__ = "season_results"
    __table_args__ = (
        UniqueConstraint(
            "season_id",
            "user_id",
            name="uq_season_results_season_user",
        ),
        UniqueConstraint(
            "season_id",
            "position",
            name="uq_season_results_season_position",
        ),
        CheckConstraint("position > 0", name="position_positive"),
        CheckConstraint("score >= 0", name="score_non_negative"),
        CheckConstraint("total_comments >= 0", name="total_comments_non_negative"),
        CheckConstraint("counted_comments >= 0", name="counted_comments_non_negative"),
        CheckConstraint("reactions >= 0", name="reactions_non_negative"),
        CheckConstraint("active_days >= 0", name="active_days_non_negative"),
        Index("ix_season_results_user_id", "user_id"),
    )

    season_id: Mapped[int] = mapped_column(
        ForeignKey("seasons.id", ondelete="RESTRICT"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(BigInteger, nullable=False)
    score: Mapped[int] = mapped_column(BigInteger, nullable=False)
    total_comments: Mapped[int] = mapped_column(BigInteger, nullable=False)
    counted_comments: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reactions: Mapped[int] = mapped_column(BigInteger, nullable=False)
    active_days: Mapped[int] = mapped_column(BigInteger, nullable=False)
    first_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
