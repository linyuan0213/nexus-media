"""rename_only_nexus_media_columns

Revision ID: b2c3d4e5f6a7
Revises: a3b4c5d6e7f8
Create Date: 2026-05-18 04:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "b2c3d4e5f6a7"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在（兼容 SQLite / MySQL / PostgreSQL）"""
    bind = op.get_bind()
    inspector = inspect(bind)
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    # DOWNLOADER 表
    if _column_exists("DOWNLOADER", "ONLY_NASTOOL"):
        with op.batch_alter_table("DOWNLOADER") as batch_op:
            batch_op.alter_column(
                "ONLY_NASTOOL",
                new_column_name="ONLY_NEXUS_MEDIA",
                existing_type=sa.Integer(),
            )
    # TORRENT_REMOVE_TASK 表
    if _column_exists("TORRENT_REMOVE_TASK", "ONLYNASTOOL"):
        with op.batch_alter_table("TORRENT_REMOVE_TASK") as batch_op:
            batch_op.alter_column(
                "ONLYNASTOOL",
                new_column_name="ONLY_NEXUS_MEDIA",
                existing_type=sa.Integer(),
            )


def downgrade():
    if _column_exists("DOWNLOADER", "ONLY_NEXUS_MEDIA"):
        with op.batch_alter_table("DOWNLOADER") as batch_op:
            batch_op.alter_column(
                "ONLY_NEXUS_MEDIA",
                new_column_name="ONLY_NASTOOL",
                existing_type=sa.Integer(),
            )
    if _column_exists("TORRENT_REMOVE_TASK", "ONLY_NEXUS_MEDIA"):
        with op.batch_alter_table("TORRENT_REMOVE_TASK") as batch_op:
            batch_op.alter_column(
                "ONLY_NEXUS_MEDIA",
                new_column_name="ONLYNASTOOL",
                existing_type=sa.Integer(),
            )
