"""download_dir_text

Revision ID: d5e6f7a8b9c0
Revises: b3c4d5e6f7a8
Create Date: 2026-06-23 20:58:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "d5e6f7a8b9c0"
down_revision: str = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = {c["name"].upper() for c in inspect(conn).get_columns(table)}
    return column.upper() in cols


def upgrade() -> None:
    if _column_exists("DOWNLOADER", "DOWNLOAD_DIR"):
        with op.batch_alter_table("DOWNLOADER", schema=None) as batch_op:
            batch_op.alter_column(
                "DOWNLOAD_DIR",
                existing_type=sa.String(length=255),
                type_=sa.Text,
                existing_nullable=False,
            )


def downgrade() -> None:
    if _column_exists("DOWNLOADER", "DOWNLOAD_DIR"):
        with op.batch_alter_table("DOWNLOADER", schema=None) as batch_op:
            batch_op.alter_column(
                "DOWNLOAD_DIR",
                existing_type=sa.Text,
                type_=sa.String(length=255),
                existing_nullable=False,
            )
