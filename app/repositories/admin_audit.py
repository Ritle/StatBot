"""Append-only administrative audit repository."""

from typing import Any

from app.models.admin_audit import AdminAuditLog
from app.repositories.base import BaseRepository


class AdminAuditRepository(BaseRepository[AdminAuditLog]):
    model: type[AdminAuditLog] = AdminAuditLog

    async def record(
        self,
        *,
        telegram_admin_id: int,
        channel_id: int,
        action: str,
        target_type: str | None = None,
        target_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdminAuditLog:
        return await self.create(
            telegram_admin_id=telegram_admin_id,
            channel_id=channel_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            metadata_json=metadata or {},
        )
