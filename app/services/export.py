"""Non-blocking CSV export of active or finalized leaderboard data."""

from __future__ import annotations

import asyncio
import csv
import io
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Channel, Season, User
from app.schemas import RatingEntry
from app.services.rating import RatingService


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    path: Path
    filename: str
    row_count: int

    async def cleanup(self) -> None:
        await asyncio.to_thread(self.path.unlink, missing_ok=True)


class ExportService:
    """Build Excel-friendly UTF-8 CSV files without blocking the event loop."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.rating = RatingService(session)

    async def create_csv(self, season: Season, channel: Channel) -> ExportArtifact:
        entries = await self.rating.get_all(season, timezone=channel.timezone)
        user_ids = [entry.user_id for entry in entries]
        users = (
            list(
                (
                    await self.session.scalars(
                        select(User).where(User.id.in_(user_ids)),
                    )
                ).all(),
            )
            if user_ids
            else []
        )
        zone = ZoneInfo(channel.timezone)
        start = season.starts_at.astimezone(zone).strftime("%Y%m%d")
        end = season.ends_at.astimezone(zone).strftime("%Y%m%d")
        filename = f"statistics_{channel.telegram_channel_id}_{start}_{end}.csv"
        path = await asyncio.to_thread(self._write_temp_csv, entries, users)
        return ExportArtifact(path=path, filename=filename, row_count=len(entries))

    @staticmethod
    def _write_temp_csv(entries: Sequence[RatingEntry], users: Sequence[User]) -> Path:
        profiles = {user.id: user for user in users}
        rows = (
            (
                entry.position,
                entry.telegram_user_id,
                profiles[entry.user_id].username or "",
                profiles[entry.user_id].first_name,
                profiles[entry.user_id].last_name or "",
                entry.total_comments,
                entry.counted_comments,
                entry.reactions,
                entry.active_days,
                entry.score,
            )
            for entry in entries
        )
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\r\n")
        writer.writerow(
            [
                "Позиция",
                "Telegram ID",
                "Username",
                "Имя",
                "Фамилия",
                "Фактические комментарии",
                "Зачтённые комментарии",
                "Реакции",
                "Активные дни",
                "Баллы",
            ],
        )
        writer.writerows(rows)
        payload = buffer.getvalue().encode("utf-8-sig")
        with tempfile.NamedTemporaryFile(prefix="statbot_", suffix=".csv", delete=False) as file:
            file.write(payload)
            return Path(file.name)
