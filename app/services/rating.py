"""Single-query activity aggregation for active and finalized seasons."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Season, SeasonStatus
from app.schemas import RatingEntry, RatingOrder, RatingPage

_LIVE_RATING_SQL = """
WITH eligible_comments AS (
    SELECT c.id, c.user_id, c.created_at, c.text_length, c.is_countable,
           (timezone(:timezone, c.created_at))::date AS local_day
      FROM comments c
      JOIN users u ON u.id = c.user_id AND u.is_bot = false
     WHERE c.channel_id = :channel_id
       AND c.created_at >= :starts_at AND c.created_at < :ends_at
       AND c.deleted_at IS NULL
       AND NOT EXISTS (
           SELECT 1 FROM excluded_users x
            WHERE x.channel_id = :channel_id AND x.user_id = c.user_id
       )
),
countable_ranked AS (
    SELECT ec.*,
           row_number() OVER (
               PARTITION BY ec.user_id, ec.local_day
               ORDER BY ec.created_at, ec.id
           ) AS daily_position
      FROM eligible_comments ec
     WHERE ec.is_countable = true AND ec.text_length >= :minimum_comment_length
),
counted_comments AS (
    SELECT * FROM countable_ranked
     WHERE CAST(:daily_comment_limit AS INTEGER) IS NULL
        OR daily_position <= CAST(:daily_comment_limit AS INTEGER)
),
comment_totals AS (
    SELECT user_id, count(*)::bigint AS total_comments
      FROM eligible_comments GROUP BY user_id
),
comment_counts AS (
    SELECT user_id, count(*)::bigint AS counted_comments
      FROM counted_comments GROUP BY user_id
),
eligible_reactions AS (
    SELECT r.user_id, r.created_at,
           (timezone(:timezone, r.created_at))::date AS local_day
      FROM current_reactions r
      JOIN posts p ON p.id = r.post_id AND p.channel_id = :channel_id
      JOIN users u ON u.id = r.user_id AND u.is_bot = false
     WHERE r.channel_id = :channel_id
       AND r.created_at >= :starts_at AND r.created_at < :ends_at
       AND NOT EXISTS (
           SELECT 1 FROM excluded_users x
            WHERE x.channel_id = :channel_id AND x.user_id = r.user_id
       )
),
reaction_counts AS (
    SELECT user_id, count(*)::bigint AS reactions
      FROM eligible_reactions GROUP BY user_id
),
activity_events AS (
    SELECT user_id, local_day, created_at FROM counted_comments
    UNION ALL
    SELECT user_id, local_day, created_at FROM eligible_reactions
),
activity_stats AS (
    SELECT user_id, count(DISTINCT local_day)::bigint AS active_days,
           min(created_at) AS first_activity_at
      FROM activity_events GROUP BY user_id
),
participants AS (
    SELECT user_id FROM comment_totals
    UNION
    SELECT user_id FROM reaction_counts
),
metrics AS (
    SELECT u.id AS user_id, u.telegram_user_id, u.first_name, u.last_name, u.username,
           coalesce(ct.total_comments, 0)::bigint AS total_comments,
           coalesce(cc.counted_comments, 0)::bigint AS counted_comments,
           coalesce(rc.reactions, 0)::bigint AS reactions,
           coalesce(ast.active_days, 0)::bigint AS active_days,
           ast.first_activity_at,
           (coalesce(cc.counted_comments, 0) * :comment_points
            + coalesce(rc.reactions, 0) * :reaction_points)::bigint AS score
      FROM participants p
      JOIN users u ON u.id = p.user_id
      LEFT JOIN comment_totals ct ON ct.user_id = p.user_id
      LEFT JOIN comment_counts cc ON cc.user_id = p.user_id
      LEFT JOIN reaction_counts rc ON rc.user_id = p.user_id
      LEFT JOIN activity_stats ast ON ast.user_id = p.user_id
),
ranked AS (
    SELECT m.*,
           row_number() OVER (
               ORDER BY score DESC, counted_comments DESC, reactions DESC,
                        active_days DESC, first_activity_at ASC NULLS LAST,
                        telegram_user_id ASC
           )::bigint AS canonical_position
      FROM metrics m
),
ordered AS (
    SELECT r.*,
           row_number() OVER (ORDER BY {order_clause})::bigint AS display_position,
           count(*) OVER ()::bigint AS total_rows
      FROM ranked r
)
SELECT * FROM ordered
{user_filter}
ORDER BY display_position
{pagination}
"""

_FINISHED_RATING_SQL = """
WITH metrics AS (
    SELECT sr.user_id, u.telegram_user_id, u.first_name, u.last_name, u.username,
           sr.total_comments, sr.counted_comments, sr.reactions, sr.active_days,
           sr.first_activity_at, sr.score, sr.position AS canonical_position
      FROM season_results sr
      JOIN users u ON u.id = sr.user_id
     WHERE sr.season_id = :season_id
),
ordered AS (
    SELECT m.*,
           row_number() OVER (ORDER BY {order_clause})::bigint AS display_position,
           count(*) OVER ()::bigint AS total_rows
      FROM metrics m
)
SELECT * FROM ordered
{user_filter}
ORDER BY display_position
{pagination}
"""

_ORDER_CLAUSES = {
    RatingOrder.SCORE: (
        "canonical_position ASC"
    ),
    RatingOrder.COMMENTS: (
        "counted_comments DESC, score DESC, reactions DESC, active_days DESC, "
        "first_activity_at ASC NULLS LAST, telegram_user_id ASC"
    ),
    RatingOrder.REACTIONS: (
        "reactions DESC, score DESC, counted_comments DESC, active_days DESC, "
        "first_activity_at ASC NULLS LAST, telegram_user_id ASC"
    ),
}


class RatingService:
    """Calculate a complete leaderboard without per-user database queries."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_page(
        self,
        season: Season,
        *,
        timezone: str,
        page: int = 0,
        page_size: int = 10,
        order: RatingOrder = RatingOrder.SCORE,
    ) -> RatingPage:
        safe_page = max(page, 0)
        safe_size = min(max(page_size, 1), 100)
        rows = await self._execute(
            season,
            timezone=timezone,
            order=order,
            pagination="LIMIT :limit OFFSET :offset",
            extra={"limit": safe_size, "offset": safe_page * safe_size},
        )
        entries = tuple(self._map_row(row) for row in rows)
        total = int(rows[0]["total_rows"]) if rows else 0
        return RatingPage(entries, total, safe_page, safe_size)

    async def get_user_entry(
        self,
        season: Season,
        telegram_user_id: int,
        *,
        timezone: str,
    ) -> RatingEntry | None:
        rows = await self._execute(
            season,
            timezone=timezone,
            order=RatingOrder.SCORE,
            user_filter="WHERE telegram_user_id = :telegram_user_id",
            extra={"telegram_user_id": telegram_user_id},
        )
        return self._map_row(rows[0], use_canonical_position=True) if rows else None

    async def get_all(self, season: Season, *, timezone: str) -> tuple[RatingEntry, ...]:
        rows = await self._execute(season, timezone=timezone, order=RatingOrder.SCORE)
        return tuple(self._map_row(row, use_canonical_position=True) for row in rows)

    async def _execute(
        self,
        season: Season,
        *,
        timezone: str,
        order: RatingOrder,
        user_filter: str = "",
        pagination: str = "",
        extra: dict[str, object] | None = None,
    ) -> list[Any]:
        template = (
            _FINISHED_RATING_SQL
            if season.status == SeasonStatus.FINISHED
            else _LIVE_RATING_SQL
        )
        query = text(
            template.format(
                order_clause=_ORDER_CLAUSES[order],
                user_filter=user_filter,
                pagination=pagination,
            ),
        )
        parameters: dict[str, object] = {"season_id": season.id}
        if season.status != SeasonStatus.FINISHED:
            parameters.update(
                channel_id=season.channel_id,
                starts_at=season.starts_at,
                ends_at=season.ends_at,
                timezone=timezone,
                minimum_comment_length=season.minimum_comment_length,
                daily_comment_limit=season.daily_comment_limit,
                comment_points=season.comment_points,
                reaction_points=season.reaction_points,
            )
        if extra:
            parameters.update(extra)
        result = await self.session.execute(query, parameters)
        return list(result.mappings().all())

    @staticmethod
    def _map_row(row: Any, *, use_canonical_position: bool = False) -> RatingEntry:
        last_name = row["last_name"]
        display_name = row["first_name"]
        if last_name:
            display_name = f"{display_name} {last_name}"
        position_key = "canonical_position" if use_canonical_position else "display_position"
        return RatingEntry(
            user_id=int(row["user_id"]),
            telegram_user_id=int(row["telegram_user_id"]),
            display_name=str(display_name),
            username=row["username"],
            position=int(row[position_key]),
            score=int(row["score"]),
            total_comments=int(row["total_comments"]),
            counted_comments=int(row["counted_comments"]),
            reactions=int(row["reactions"]),
            active_days=int(row["active_days"]),
            first_activity_at=row["first_activity_at"],
        )
