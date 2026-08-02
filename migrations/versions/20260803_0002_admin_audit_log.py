"""Add structured administrative audit log.

Revision ID: 20260803_0002
Revises: 20260731_0001
Create Date: 2026-08-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260803_0002"
down_revision: str | None = "20260731_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admin_audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("telegram_admin_id", sa.BigInteger(), nullable=False),
        sa.Column("channel_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=True),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["channel_id"],
            ["channels.id"],
            name=op.f("fk_admin_audit_log_channel_id_channels"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_admin_audit_log")),
    )
    op.create_index(
        "ix_admin_audit_channel_created_at",
        "admin_audit_log",
        ["channel_id", "created_at"],
    )
    op.create_index(
        "ix_admin_audit_admin_created_at",
        "admin_audit_log",
        ["telegram_admin_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_admin_audit_admin_created_at", table_name="admin_audit_log")
    op.drop_index("ix_admin_audit_channel_created_at", table_name="admin_audit_log")
    op.drop_table("admin_audit_log")
