"""Domain enumerations persisted by PostgreSQL."""

from enum import StrEnum


class SeasonStatus(StrEnum):
    """Lifecycle of a rating season."""

    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"
