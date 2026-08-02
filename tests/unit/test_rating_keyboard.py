"""Pagination keyboard behavior."""

from app.bot.keyboards import rating_keyboard
from app.schemas import RatingOrder


def test_middle_rating_page_has_back_forward_refresh_and_personal_buttons() -> None:
    keyboard = rating_keyboard(
        channel_id=1,
        season_id=2,
        page=1,
        pages=3,
        order=RatingOrder.SCORE,
    )

    labels = [button.text for row in keyboard.inline_keyboard for button in row]
    assert labels == ["⬅️", "➡️", "🔄", "👤 Моё место"]
