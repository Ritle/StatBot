"""Expected rating-period lifecycle failures."""


class SeasonError(Exception):
    """A season command cannot be completed in the current state."""
