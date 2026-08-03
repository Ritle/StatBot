"""Harden rating indexes and finalized result storage.

Revision ID: 20260803_0003
Revises: 20260803_0002
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260803_0003"
down_revision: str | None = "20260803_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESULT_COLUMNS = (
    "position",
    "score",
    "total_comments",
    "counted_comments",
    "reactions",
    "active_days",
)


def upgrade() -> None:
    op.create_index(
        "ix_comments_channel_telegram_message",
        "comments",
        ["channel_id", "telegram_message_id"],
    )
    op.create_index(
        "ix_current_reactions_channel_created_at",
        "current_reactions",
        ["channel_id", "created_at"],
    )

    op.drop_constraint(
        "fk_admin_audit_log_channel_id_channels",
        "admin_audit_log",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_admin_audit_log_channel_id_channels",
        "admin_audit_log",
        "channels",
        ["channel_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint(
        "fk_season_results_season_id_seasons",
        "season_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_season_results_season_id_seasons",
        "season_results",
        "seasons",
        ["season_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    for column in _RESULT_COLUMNS:
        op.alter_column(
            "season_results",
            column,
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
            postgresql_using=f"{column}::bigint",
        )


def downgrade() -> None:
    for column in reversed(_RESULT_COLUMNS):
        op.alter_column(
            "season_results",
            column,
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
            postgresql_using=f"{column}::integer",
        )

    op.drop_constraint(
        "fk_season_results_season_id_seasons",
        "season_results",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_season_results_season_id_seasons",
        "season_results",
        "seasons",
        ["season_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(
        "fk_admin_audit_log_channel_id_channels",
        "admin_audit_log",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_admin_audit_log_channel_id_channels",
        "admin_audit_log",
        "channels",
        ["channel_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_index(
        "ix_current_reactions_channel_created_at",
        table_name="current_reactions",
    )
    op.drop_index(
        "ix_comments_channel_telegram_message",
        table_name="comments",
    )
