"""Tracked Telegram channel model."""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, IdMixin, TimestampMixin


class Channel(IdMixin, TimestampMixin, Base):
    """A channel and its optional linked discussion chat."""

    __tablename__ = "channels"

    telegram_channel_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str | None] = mapped_column(String(32))
    discussion_chat_id: Mapped[int | None] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="Europe/Amsterdam",
        server_default=text("'Europe/Amsterdam'"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
