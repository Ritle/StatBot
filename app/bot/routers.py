"""Root Telegram router."""

from aiogram import Router

from app.bot.handlers.activity import router as activity_router
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.common import router as common_router
from app.bot.handlers.exclusions import router as exclusions_router
from app.bot.handlers.rating import router as rating_router
from app.bot.handlers.seasons import router as seasons_router
from app.bot.handlers.settings import router as settings_router

ALLOWED_UPDATES: tuple[str, ...] = (
    "message",
    "channel_post",
    "callback_query",
    "message_reaction",
)

root_router = Router(name="root")
root_router.include_router(admin_router)
root_router.include_router(seasons_router)
root_router.include_router(settings_router)
root_router.include_router(exclusions_router)
root_router.include_router(rating_router)
root_router.include_router(common_router)
root_router.include_router(activity_router)
