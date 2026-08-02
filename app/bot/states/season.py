"""FSM states for season draft creation."""

from aiogram.fsm.state import State, StatesGroup


class SeasonCreateStates(StatesGroup):
    name = State()
    starts_at = State()
    ends_at = State()
    comment_points = State()
    reaction_points = State()
    daily_comment_limit = State()
    minimum_comment_length = State()
    confirmation = State()
