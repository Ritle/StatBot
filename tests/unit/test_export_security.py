"""CSV and Telegram request hardening tests."""

from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import GetMe, Response

from app.bot.middlewares import RetryAfterMiddleware
from app.services.export import safe_csv_text


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
def test_csv_formula_prefixes_are_neutralized(prefix: str) -> None:
    assert safe_csv_text(f"{prefix}formula") == f"'{prefix}formula"


def test_regular_csv_text_is_unchanged() -> None:
    assert safe_csv_text("Иван, тест") == "Иван, тест"


async def test_telegram_retry_after_is_bounded() -> None:
    method = GetMe()
    expected = cast("Response[Any]", object())
    request: Any = AsyncMock(
        side_effect=[TelegramRetryAfter(method, "rate limit", 1), expected],
    )
    sleep = AsyncMock()

    with patch("app.bot.middlewares.rate_limit.asyncio.sleep", sleep):
        result = await RetryAfterMiddleware(max_retries=1)(
            request,
            cast("Bot", object()),
            method,
        )

    assert result is expected
    sleep.assert_awaited_once_with(1)
    assert request.await_count == 2


async def test_long_telegram_retry_after_is_not_slept() -> None:
    method = GetMe()
    request: Any = AsyncMock(
        side_effect=TelegramRetryAfter(method, "rate limit", 120),
    )
    sleep = AsyncMock()

    with (
        patch("app.bot.middlewares.rate_limit.asyncio.sleep", sleep),
        pytest.raises(TelegramRetryAfter),
    ):
        await RetryAfterMiddleware(max_retries=2, max_wait_seconds=30)(
            request,
            cast("Bot", object()),
            method,
        )

    sleep.assert_not_awaited()
