"""add_state_to_download_history

Revision ID: c1d2e3f4a5b6
Revises: b2c3d4e5f6a7
Create Date: 2026-05-19 14:35:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "c1d2e3f4a5b6"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _column_exists(table_name: str, column_name: str) -> bool:
    """检查列是否存在（兼容 SQLite / MySQL / PostgreSQL）"""
    bind = op.get_bind()
    inspector = inspect(bind)
    if not inspector.has_table(table_name):
        return False
    columns = [c["name"] for c in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade() -> None:
    # 添加 DOWNLOAD_HISTORY 表的 STATE 列，历史任务默认标记为已完成
    if not _column_exists("DOWNLOAD_HISTORY", "STATE"):
        with op.batch_alter_table("DOWNLOAD_HISTORY") as batch_op:
            batch_op.add_column(sa.Column("STATE", sa.String(20), nullable=False, server_default="downloading"))


def downgrade() -> None:
    if _column_exists("DOWNLOAD_HISTORY", "STATE"):
        with op.batch_alter_table("DOWNLOAD_HISTORY") as batch_op:
            batch_op.drop_column("STATE")
