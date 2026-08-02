"""Safe conversion between channel-local wall time and UTC."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo


class LocalTimeError(ValueError):
    """A wall time is invalid or ambiguous in the requested timezone."""


def parse_local_datetime(value: str, timezone: str) -> datetime:
    """Parse DD.MM.YYYY HH:MM and reject DST gaps or ambiguous wall times."""
    try:
        naive = datetime.strptime(value.strip(), "%d.%m.%Y %H:%M")
    except ValueError as error:
        raise LocalTimeError("используйте формат ДД.ММ.ГГГГ ЧЧ:ММ") from error

    zone = ZoneInfo(timezone)
    valid: list[datetime] = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(UTC).astimezone(zone)
        if (
            round_trip.replace(tzinfo=None) == naive
            and candidate.utcoffset() == round_trip.utcoffset()
        ):
            valid.append(candidate)
    unique_offsets = {candidate.utcoffset() for candidate in valid}
    if not valid:
        raise LocalTimeError("это локальное время не существует из-за перехода на летнее время")
    if len(unique_offsets) > 1:
        raise LocalTimeError("это локальное время неоднозначно из-за перехода на зимнее время")
    return valid[0].astimezone(UTC)


def format_local_datetime(value: datetime, timezone: str) -> str:
    """Render an aware timestamp in a channel's configured timezone."""
    return value.astimezone(ZoneInfo(timezone)).strftime("%d.%m.%Y %H:%M")
