"""Basic user commands."""

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name=__name__)


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Describe the bot's purpose."""
    await message.answer(
        "Привет! Я собираю активность участников Telegram-канала.\n"
        "Используйте /setup для подключения канала и /help для справки.",
    )


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Show currently available commands."""
    await message.answer(
        "<b>Доступные команды</b>\n"
        "/start — начать работу\n"
        "/help — показать эту справку\n"
        "/setup — подключить канал и группу обсуждений\n"
        "/status — проверить конфигурацию и сбор событий\n"
        "/settings — открыть административное меню\n"
        "/create_season — создать период рейтинга\n"
        "/start_season, /finish_season, /cancel_season — управлять периодом\n"
        "/seasons, /period — список и текущий период\n"
        "/rating, /me — рейтинг и личная статистика\n"
        "/top_comments, /top_reactions — лидеры по типу активности\n"
        "/exclude, /include — управлять исключениями\n"
        "/export — выгрузить статистику CSV",
    )
