"""Tests for local wall-time conversion around DST transitions."""

from datetime import UTC, datetime

import pytest

from app.utils.datetime import LocalTimeError, parse_local_datetime


def test_local_datetime_is_converted_to_utc() -> None:
    assert parse_local_datetime("01.08.2026 12:00", "Europe/Amsterdam") == datetime(
        2026,
        8,
        1,
        10,
        0,
        tzinfo=UTC,
    )


def test_nonexistent_summer_transition_time_is_rejected() -> None:
    with pytest.raises(LocalTimeError, match="не существует"):
        parse_local_datetime("29.03.2026 02:30", "Europe/Amsterdam")


def test_ambiguous_winter_transition_time_is_rejected() -> None:
    with pytest.raises(LocalTimeError, match="неоднозначно"):
        parse_local_datetime("25.10.2026 02:30", "Europe/Amsterdam")
