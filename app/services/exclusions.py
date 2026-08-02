"""Administrative per-channel rating exclusions."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AdminOperationError
from app.models import ExcludedUser, User
from app.repositories import ExcludedUserRepository, UserRepository
from app.services.audit import AdminAction, AuditService


class ExclusionService:
    """Resolve known users and mutate exclusions without deleting activity."""

    def __init__(self, session: AsyncSession) -> None:
        self.users = UserRepository(session)
        self.exclusions = ExcludedUserRepository(session)
        self.audit = AuditService(session)

    async def find_known_users(self, identifier: str) -> list[User]:
        raw = identifier.strip()
        try:
            telegram_user_id = int(raw)
        except ValueError:
            return await self.users.find_by_username(raw)
        if telegram_user_id <= 0 or telegram_user_id > 2**63 - 1:
            return []
        user = await self.users.get_by_telegram_id(telegram_user_id)
        return [user] if user is not None else []

    async def exclude(
        self,
        *,
        channel_id: int,
        user: User,
        admin_user: User,
        telegram_admin_id: int,
        reason: str | None,
    ) -> ExcludedUser:
        if user.is_bot:
            raise AdminOperationError("боты и так не участвуют в персональном рейтинге")
        normalized_reason = reason.strip() if reason else None
        if normalized_reason and len(normalized_reason) > 500:
            raise AdminOperationError("причина не должна превышать 500 символов")
        exclusion = await self.exclusions.get_by_channel_and_user(channel_id, user.id)
        if exclusion is None:
            exclusion = await self.exclusions.create(
                channel_id=channel_id,
                user_id=user.id,
                reason=normalized_reason,
                created_by=admin_user.id,
            )
        else:
            exclusion = await self.exclusions.update(
                exclusion,
                reason=normalized_reason,
                created_by=admin_user.id,
            )
        await self.audit.record(
            admin_id=telegram_admin_id,
            channel_id=channel_id,
            action=AdminAction.EXCLUDE_USER,
            target_type="user",
            target_id=user.id,
            metadata={"has_reason": bool(normalized_reason)},
        )
        return exclusion

    async def include(
        self,
        *,
        channel_id: int,
        user: User,
        telegram_admin_id: int,
    ) -> bool:
        removed = await self.exclusions.remove(channel_id, user.id)
        if removed:
            await self.audit.record(
                admin_id=telegram_admin_id,
                channel_id=channel_id,
                action=AdminAction.INCLUDE_USER,
                target_type="user",
                target_id=user.id,
            )
        return removed
