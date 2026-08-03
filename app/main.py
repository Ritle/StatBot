"""Application entry point."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from pydantic import ValidationError
from pydantic_settings import SettingsError

from app.bot.handlers.errors import handle_unexpected_error
from app.bot.middlewares import RetryAfterMiddleware
from app.bot.routers import ALLOWED_UPDATES, root_router
from app.config import BotMode, Settings, load_settings
from app.database.session import Database
from app.logging import configure_logging

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    """Build a dispatcher without starting network operations."""
    dispatcher = Dispatcher()
    dispatcher.errors.register(handle_unexpected_error)
    dispatcher.include_router(root_router)
    dispatcher.startup.register(on_startup)
    dispatcher.shutdown.register(on_shutdown)
    return dispatcher


async def on_startup(bot: Bot, database: Database) -> None:
    """Check infrastructure before accepting Telegram updates."""
    await database.check_connection()
    bot_info = await bot.get_me()
    logger.info("Application started for bot @%s", bot_info.username)


async def on_shutdown() -> None:
    """Report that the dispatcher has stopped accepting updates."""
    logger.info("Dispatcher shutdown hook completed")


async def run(settings: Settings) -> None:
    """Run the bot in long-polling mode."""
    if settings.bot_mode is not BotMode.POLLING:
        raise RuntimeError("Webhook mode is configured but is not implemented yet")

    telegram_session = AiohttpSession(timeout=30)
    telegram_session.middleware(RetryAfterMiddleware())
    bot = Bot(
        token=settings.bot_token.get_secret_value(),
        session=telegram_session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        database = Database(settings.sqlalchemy_url)
        dispatcher = create_dispatcher()
        try:
            await dispatcher.start_polling(
                bot,
                database=database,
                settings=settings,
                allowed_updates=list(ALLOWED_UPDATES),
                handle_as_tasks=False,
                handle_signals=True,
                close_bot_session=False,
            )
        finally:
            await database.dispose()
    finally:
        await bot.session.close()
        logger.info("Application stopped")


def main() -> None:
    """Load configuration and run the async application."""
    configure_logging()
    try:
        settings = load_settings()
    except (SettingsError, ValidationError):
        logger.error("Application configuration is invalid")
        raise SystemExit(2) from None

    configure_logging(settings.log_level)
    logger.info("Starting application in %s mode", settings.bot_mode.value)
    try:
        asyncio.run(run(settings))
    except KeyboardInterrupt:
        logger.info("Application interrupted")
    except TelegramAPIError:
        logger.exception("Telegram API error stopped the application")
        raise SystemExit(1) from None
    except Exception:
        logger.exception("Unhandled exception stopped the application")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
