"""Bot assembly tests."""

from app.bot.routers import ALLOWED_UPDATES
from app.main import create_dispatcher


def test_dispatcher_contains_basic_and_reaction_updates() -> None:
    dispatcher = create_dispatcher()

    assert dispatcher.sub_routers
    assert dispatcher.errors.handlers
    assert ALLOWED_UPDATES == (
        "message",
        "channel_post",
        "callback_query",
        "message_reaction",
    )
