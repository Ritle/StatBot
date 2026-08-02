"""FSM states for private channel setup."""

from aiogram.fsm.state import State, StatesGroup


class SetupStates(StatesGroup):
    waiting_for_chat = State()
