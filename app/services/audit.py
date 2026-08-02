"""Safe structured audit facade used by privileged services."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AdminAuditLog
from app.repositories import AdminAuditRepository


class AdminAction(StrEnum):
    SETUP_CHANNEL = "setup_channel"
    CREATE_SEASON = "create_season"
    START_SEASON = "start_season"
    FINISH_SEASON = "finish_season"
    CANCEL_SEASON = "cancel_season"
    UPDATE_RULES = "update_rules"
    EXCLUDE_USER = "exclude_user"
    INCLUDE_USER = "include_user"
    RECALCULATE = "recalculate"
    EXPORT = "export"


class AuditService:
    """Persist whitelisted action data without secrets or connection details."""

    def __init__(self, session: AsyncSession) -> None:
        self.repository = AdminAuditRepository(session)

    async def record(
        self,
        *,
        admin_id: int,
        channel_id: int,
        action: AdminAction,
        target_type: str | None = None,
        target_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AdminAuditLog:
        return await self.repository.record(
            telegram_admin_id=admin_id,
            channel_id=channel_id,
            action=action.value,
            target_type=target_type,
            target_id=target_id,
            metadata=metadata,
        )
