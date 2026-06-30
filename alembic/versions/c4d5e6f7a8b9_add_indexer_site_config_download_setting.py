"""add indexer_site_config download_setting

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-30

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, None] = "f6f7a8b9c0d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(conn, table_name: str) -> bool:
    return inspect(conn).has_table(table_name)


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    columns = inspect(conn).get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    conn = op.get_bind()
    table_name = "INDEXER_SITE_CONFIG"

    if not _table_exists(conn, table_name):
        op.create_table(
            table_name,
            sa.Column("ID", sa.Integer(), nullable=False),
            sa.Column("SITE_NAME", sa.String(length=255), nullable=False),
            sa.Column("SOURCE", sa.String(length=50), nullable=False),
            sa.Column("PUBLIC", sa.Integer(), nullable=True),
            sa.Column("DOWNLOAD_SETTING", sa.Integer(), nullable=True),
            sa.Column("ENABLED", sa.Integer(), nullable=True),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
            sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("ID"),
            sa.UniqueConstraint("SITE_NAME", name="UQ_INDEXER_SITE_CONFIG_SITE_NAME"),
        )
    elif not _column_exists(conn, table_name, "DOWNLOAD_SETTING"):
        op.add_column(
            table_name,
            sa.Column("DOWNLOAD_SETTING", sa.Integer(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    table_name = "INDEXER_SITE_CONFIG"

    if _table_exists(conn, table_name) and _column_exists(conn, table_name, "DOWNLOAD_SETTING"):
        op.drop_column(table_name, "DOWNLOAD_SETTING")
