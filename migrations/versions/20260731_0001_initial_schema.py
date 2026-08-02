"""Create the initial activity tracking schema.

Revision ID: 20260731_0001
Revises:
Create Date: 2026-07-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

season_status = postgresql.ENUM(
    "draft",
    "active",
    "finished",
    "cancelled",
    name="season_status",
    create_type=False,
)


def _id_column() -> sa.Column[int]:
    return sa.Column(
        "id",
        sa.BigInteger(),
        sa.Identity(always=False),
        nullable=False,
    )


def _created_at_column() -> sa.Column[object]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def _updated_at_column() -> sa.Column[object]:
    return sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    """Create enums, tables, constraints, and query indexes."""
    season_status.create(op.get_bind(), checkfirst=False)

    op.create_table(
        "channels",
        _id_column(),
        sa.Column("telegram_channel_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("discussion_chat_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'Europe/Amsterdam'"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_channels")),
    )
    op.create_index(
        op.f("ix_channels_telegram_channel_id"),
        "channels",
        ["telegram_channel_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_channels_discussion_chat_id"),
        "channels",
        ["discussion_chat_id"],
        unique=True,
    )

    op.create_table(
        "users",
        _id_column(),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        op.f("ix_users_telegram_user_id"),
        "users",
        ["telegram_user_id"],
        unique=True,
    )

    op.create_table(
        "posts",
        _id_column(),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("discussion_message_id", sa.BigInteger(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_posts_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_posts")),
        sa.UniqueConstraint(
            "channel_id",
            "telegram_message_id",
            name="uq_posts_channel_telegram_message",
        ),
    )
    op.create_index(
        "ix_posts_channel_discussion_message",
        "posts",
        ["channel_id", "discussion_message_id"],
        unique=False,
    )

    op.create_table(
        "comments",
        _id_column(),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("discussion_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("reply_to_message_id", sa.BigInteger(), nullable=True),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_countable",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        _created_at_column(),
        sa.CheckConstraint(
            "text_length >= 0",
            name=op.f("ck_comments_text_length_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_comments_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_comments_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_comments_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_comments")),
        sa.UniqueConstraint(
            "discussion_chat_id",
            "telegram_message_id",
            name="uq_comments_discussion_message",
        ),
    )
    op.create_index(
        "ix_comments_channel_created_at",
        "comments",
        ["channel_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_comments_user_created_at",
        "comments",
        ["user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_comments_post_user_created_at",
        "comments",
        ["post_id", "user_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "reaction_events",
        _id_column(),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_update_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "old_reactions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "new_reactions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_reaction_events_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_reaction_events_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reaction_events_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reaction_events")),
    )
    op.create_index(
        "ix_reaction_events_channel_created_at",
        "reaction_events",
        ["channel_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_reaction_events_post_user_created_at",
        "reaction_events",
        ["post_id", "user_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_reaction_events_telegram_update_id",
        "reaction_events",
        ["telegram_update_id"],
        unique=True,
        postgresql_where=sa.text("telegram_update_id IS NOT NULL"),
    )

    op.create_table(
        "current_reactions",
        _id_column(),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("reaction_key", sa.String(length=512), nullable=False),
        _created_at_column(),
        _updated_at_column(),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_current_reactions_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["post_id"],
            ["posts.id"],
            name=op.f("fk_current_reactions_post_id_posts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_current_reactions_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_current_reactions")),
        sa.UniqueConstraint(
            "channel_id",
            "post_id",
            "user_id",
            "reaction_key",
            name="uq_current_reactions_actor_key",
        ),
    )
    op.create_index(
        "ix_current_reactions_post_user",
        "current_reactions",
        ["post_id", "user_id"],
        unique=False,
    )

    op.create_table(
        "seasons",
        _id_column(),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            season_status,
            server_default=sa.text("'draft'"),
            nullable=False,
        ),
        sa.Column(
            "comment_points",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "reaction_points",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("daily_comment_limit", sa.Integer(), nullable=True),
        sa.Column(
            "minimum_comment_length",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        _updated_at_column(),
        sa.CheckConstraint(
            "comment_points >= 0",
            name=op.f("ck_seasons_comment_points_non_negative"),
        ),
        sa.CheckConstraint(
            "daily_comment_limit IS NULL OR daily_comment_limit > 0",
            name=op.f("ck_seasons_daily_comment_limit_positive"),
        ),
        sa.CheckConstraint(
            "minimum_comment_length >= 0",
            name=op.f("ck_seasons_minimum_comment_length_non_negative"),
        ),
        sa.CheckConstraint(
            "reaction_points >= 0",
            name=op.f("ck_seasons_reaction_points_non_negative"),
        ),
        sa.CheckConstraint(
            "ends_at > starts_at",
            name=op.f("ck_seasons_valid_date_range"),
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_seasons_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_seasons")),
    )
    op.create_index(
        "ix_seasons_channel_status",
        "seasons",
        ["channel_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_seasons_status_date_range",
        "seasons",
        ["status", "starts_at", "ends_at"],
        unique=False,
    )
    op.create_index(
        "uq_seasons_one_active_per_channel",
        "seasons",
        ["channel_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "excluded_users",
        _id_column(),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("created_by", sa.BigInteger(), nullable=False),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_excluded_users_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_excluded_users_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_excluded_users_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_excluded_users")),
        sa.UniqueConstraint(
            "channel_id",
            "user_id",
            name="uq_excluded_users_channel_user",
        ),
    )
    op.create_index(
        "ix_excluded_users_user_id",
        "excluded_users",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "season_results",
        _id_column(),
        sa.Column("season_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("total_comments", sa.Integer(), nullable=False),
        sa.Column("counted_comments", sa.Integer(), nullable=False),
        sa.Column("reactions", sa.Integer(), nullable=False),
        sa.Column("active_days", sa.Integer(), nullable=False),
        sa.Column("first_activity_at", sa.DateTime(timezone=True), nullable=True),
        _created_at_column(),
        sa.CheckConstraint(
            "active_days >= 0",
            name=op.f("ck_season_results_active_days_non_negative"),
        ),
        sa.CheckConstraint(
            "counted_comments >= 0",
            name=op.f("ck_season_results_counted_comments_non_negative"),
        ),
        sa.CheckConstraint(
            "position > 0",
            name=op.f("ck_season_results_position_positive"),
        ),
        sa.CheckConstraint(
            "reactions >= 0",
            name=op.f("ck_season_results_reactions_non_negative"),
        ),
        sa.CheckConstraint(
            "score >= 0",
            name=op.f("ck_season_results_score_non_negative"),
        ),
        sa.CheckConstraint(
            "total_comments >= 0",
            name=op.f("ck_season_results_total_comments_non_negative"),
        ),
        sa.ForeignKeyConstraint(
            ["season_id"],
            ["seasons.id"],
            name=op.f("fk_season_results_season_id_seasons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_season_results_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_season_results")),
        sa.UniqueConstraint(
            "season_id",
            "position",
            name="uq_season_results_season_position",
        ),
        sa.UniqueConstraint(
            "season_id",
            "user_id",
            name="uq_season_results_season_user",
        ),
    )
    op.create_index(
        "ix_season_results_user_id",
        "season_results",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop all activity tracking objects in dependency order."""
    op.drop_index("ix_season_results_user_id", table_name="season_results")
    op.drop_table("season_results")

    op.drop_index("ix_excluded_users_user_id", table_name="excluded_users")
    op.drop_table("excluded_users")

    op.drop_index(
        "uq_seasons_one_active_per_channel",
        table_name="seasons",
        postgresql_where=sa.text("status = 'active'"),
    )
    op.drop_index("ix_seasons_status_date_range", table_name="seasons")
    op.drop_index("ix_seasons_channel_status", table_name="seasons")
    op.drop_table("seasons")

    op.drop_index(
        "ix_current_reactions_post_user",
        table_name="current_reactions",
    )
    op.drop_table("current_reactions")

    op.drop_index(
        "uq_reaction_events_telegram_update_id",
        table_name="reaction_events",
        postgresql_where=sa.text("telegram_update_id IS NOT NULL"),
    )
    op.drop_index(
        "ix_reaction_events_post_user_created_at",
        table_name="reaction_events",
    )
    op.drop_index(
        "ix_reaction_events_channel_created_at",
        table_name="reaction_events",
    )
    op.drop_table("reaction_events")

    op.drop_index(
        "ix_comments_post_user_created_at",
        table_name="comments",
    )
    op.drop_index("ix_comments_user_created_at", table_name="comments")
    op.drop_index("ix_comments_channel_created_at", table_name="comments")
    op.drop_table("comments")

    op.drop_index(
        "ix_posts_channel_discussion_message",
        table_name="posts",
    )
    op.drop_table("posts")

    op.drop_index(op.f("ix_users_telegram_user_id"), table_name="users")
    op.drop_table("users")

    op.drop_index(op.f("ix_channels_discussion_chat_id"), table_name="channels")
    op.drop_index(op.f("ix_channels_telegram_channel_id"), table_name="channels")
    op.drop_table("channels")

    season_status.drop(op.get_bind(), checkfirst=False)
