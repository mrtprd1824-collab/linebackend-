# migrations/versions/20251019_01_create_change_logs_table.py - สร้างตาราง change_logs
"""create change_logs table

Revision ID: 20251019_01
Revises: 8b15f7c4c0e8
Create Date: 2025-10-19 05:45:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251019_01"
down_revision: Union[str, None] = "8b15f7c4c0e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "change_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["user.id"]),
    )
    op.create_index("ix_change_logs_created_at", "change_logs", [sa.text("created_at DESC")])
    op.create_index(
        op.f("ix_change_logs_created_by_admin_id"),
        "change_logs",
        ["created_by_admin_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_change_logs_created_by_admin_id"), table_name="change_logs")
    op.drop_index("ix_change_logs_created_at", table_name="change_logs")
    op.drop_table("change_logs")
