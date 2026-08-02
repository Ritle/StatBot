"""FSM states for rule editing and ambiguous exclusion choices."""

from aiogram.fsm.state import State, StatesGroup


class RuleEditStates(StatesGroup):
    value = State()
    confirmation = State()


class ExclusionStates(StatesGroup):
    choice = State()
