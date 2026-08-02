"""Global Telegram update error handler."""

import logging

from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    """Log an exception without exposing it to Telegram users."""
    logger.error(
        "Unhandled exception while processing Telegram update",
        exc_info=event.exception,
    )
    return True
