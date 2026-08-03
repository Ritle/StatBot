"""Bounded retry handling for Telegram flood-control responses."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.client.session.middlewares.base import (
    BaseRequestMiddleware,
    NextRequestMiddlewareType,
)
from aiogram.exceptions import TelegramRetryAfter
from aiogram.methods import Response, TelegramMethod
from aiogram.methods.base import TelegramType

logger = logging.getLogger(__name__)


class RetryAfterMiddleware(BaseRequestMiddleware):
    """Retry 429 responses a bounded number of times without logging payloads."""

    def __init__(self, *, max_retries: int = 2, max_wait_seconds: int = 30) -> None:
        self.max_retries = max_retries
        self.max_wait_seconds = max_wait_seconds

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        for attempt in range(self.max_retries + 1):
            try:
                return await make_request(bot, method)
            except TelegramRetryAfter as error:
                if attempt >= self.max_retries or error.retry_after > self.max_wait_seconds:
                    raise
                logger.warning(
                    "Telegram rate limit for %s; retry %s/%s in %s seconds",
                    type(method).__name__,
                    attempt + 1,
                    self.max_retries,
                    error.retry_after,
                )
                await asyncio.sleep(error.retry_after)
        raise RuntimeError("unreachable Telegram retry state")
