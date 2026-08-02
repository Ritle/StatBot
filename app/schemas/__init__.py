"""Application data-transfer schemas."""

from app.schemas.rating import RatingEntry, RatingOrder, RatingPage
from app.schemas.telegram import TelegramCommentData, TelegramPostData, TelegramUserData

__all__ = [
    "RatingEntry",
    "RatingOrder",
    "RatingPage",
    "TelegramCommentData",
    "TelegramPostData",
    "TelegramUserData",
]
