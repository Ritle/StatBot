"""Read models returned by the rating SQL service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class RatingOrder(StrEnum):
    SCORE = "score"
    COMMENTS = "comments"
    REACTIONS = "reactions"


@dataclass(frozen=True, slots=True)
class RatingEntry:
    user_id: int
    telegram_user_id: int
    display_name: str
    username: str | None
    position: int
    score: int
    total_comments: int
    counted_comments: int
    reactions: int
    active_days: int
    first_activity_at: datetime | None


@dataclass(frozen=True, slots=True)
class RatingPage:
    entries: tuple[RatingEntry, ...]
    total: int
    page: int
    page_size: int
