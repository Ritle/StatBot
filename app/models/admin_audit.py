"""Structured audit trail for administrative actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base, CreatedAtMixin, IdMixin


class AdminAuditLog(IdMixin, CreatedAtMixin, Base):
    """Append-only safe metadata about a privileged operation."""

    __tablename__ = "admin_audit_log"
    __table_args__ = (
        Index("ix_admin_audit_channel_created_at", "channel_id", "created_at"),
        Index("ix_admin_audit_admin_created_at", "telegram_admin_id", "created_at"),
    )

    telegram_admin_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(64))
    target_id: Mapped[int | None] = mapped_column(BigInteger)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
