# migrations/versions/20251019_02_add_changelog_files_table.py - สร้างตารางแนบไฟล์ changelog
"""add changelog files table

Revision ID: 20251019_02
Revises: 20251019_01
Create Date: 2025-10-19 06:40:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20251019_02"
down_revision: Union[str, None] = "20251019_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "change_log_files",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("change_log_id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_url", sa.String(length=1024), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["change_log_id"], ["change_logs.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_change_log_files_change_log_id"), "change_log_files", ["change_log_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_change_log_files_change_log_id"), table_name="change_log_files")
    op.drop_table("change_log_files")
