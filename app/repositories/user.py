"""User repository."""

from typing import cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    """Persistence operations for Telegram users."""

    model: type[User] = User

    async def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        statement = select(User).where(User.telegram_user_id == telegram_user_id)
        return cast("User | None", await self.session.scalar(statement))

    async def telegram_id_exists(self, telegram_user_id: int) -> bool:
        return await self.exists(User.telegram_user_id == telegram_user_id)

    async def find_by_username(self, username: str) -> list[User]:
        """Search only locally known current profiles, case-insensitively."""
        normalized = username.removeprefix("@").strip().lower()
        if not normalized:
            return []
        statement = (
            select(User)
            .where(func.lower(User.username) == normalized)
            .order_by(User.telegram_user_id)
        )
        return list((await self.session.scalars(statement)).all())

    async def upsert_telegram_user(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        first_name: str,
        last_name: str | None,
        is_bot: bool,
    ) -> User:
        """Create a Telegram user or refresh mutable profile fields."""
        profile = {
            "username": username,
            "first_name": first_name,
            "last_name": last_name,
            "is_bot": is_bot,
        }
        statement = (
            insert(User)
            .values(telegram_user_id=telegram_user_id, **profile)
            .on_conflict_do_update(
                index_elements=[User.telegram_user_id],
                set_={**profile, "updated_at": func.now()},
            )
            .returning(User.id)
        )
        user_id = await self.session.scalar(statement)
        if user_id is None:  # pragma: no cover
            raise RuntimeError("user upsert did not return an identifier")
        user = await self.get_by_id(user_id)
        if user is None:  # pragma: no cover
            raise RuntimeError("upserted user could not be loaded")
        await self.session.refresh(user)
        return user
