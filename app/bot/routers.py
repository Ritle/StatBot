"""Root Telegram router."""

from aiogram import Router

from app.bot.handlers.activity import router as activity_router
from app.bot.handlers.admin import router as admin_router
from app.bot.handlers.common import router as common_router

ALLOWED_UPDATES: tuple[str, ...] = (
    "message",
    "edited_message",
    "channel_post",
    "edited_channel_post",
    "callback_query",
    "my_chat_member",
    "chat_member",
    "message_reaction",
    "message_reaction_count",
)

root_router = Router(name="root")
root_router.include_router(admin_router)
root_router.include_router(common_router)
root_router.include_router(activity_router)
