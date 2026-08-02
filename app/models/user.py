"""Telegram user persistence model."""

from __future__ import annotations

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, IdMixin, TimestampMixin


class User(IdMixin, TimestampMixin, Base):
    """A Telegram user known to the application."""

    __tablename__ = "users"

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger,
        unique=True,
        index=True,
        nullable=False,
    )
    username: Mapped[str | None] = mapped_column(String(32))
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    is_bot: Mapped[bool] = mapped_column(default=False, nullable=False)
