"""Administrative permission and callback-expiration tests."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from app.bot.handlers.seasons import _creation_expired, _nonnegative_integer
from app.bot.handlers.settings import _fsm_expired
from app.services.permissions import TelegramPermissionService


async def test_channel_administrator_is_allowed() -> None:
    bot: Any = SimpleNamespace(
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(status=ChatMemberStatus.ADMINISTRATOR),
        ),
    )
    service = TelegramPermissionService(cast("Bot", bot), frozenset())

    assert await service.is_channel_administrator(10, -1001) is True


async def test_superadministrator_bypasses_chat_lookup() -> None:
    bot: Any = SimpleNamespace(get_chat_member=AsyncMock())
    service = TelegramPermissionService(cast("Bot", bot), frozenset({10}))

    assert await service.is_channel_administrator(10, -1001) is True
    bot.get_chat_member.assert_not_awaited()


async def test_regular_member_is_rejected() -> None:
    bot: Any = SimpleNamespace(
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(status=ChatMemberStatus.MEMBER),
        ),
    )
    service = TelegramPermissionService(cast("Bot", bot), frozenset())

    assert await service.is_channel_administrator(10, -1001) is False


def test_expired_fsm_payload_is_rejected() -> None:
    assert _fsm_expired(
        {"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
    )


def test_fresh_fsm_payload_is_accepted() -> None:
    assert not _fsm_expired(
        {"expires_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat()},
    )


def test_season_creation_expiration_and_integer_bounds() -> None:
    assert _creation_expired({"expires_at": "invalid"})
    assert _nonnegative_integer("2147483647") == 2_147_483_647
    assert _nonnegative_integer("2147483648") is None
