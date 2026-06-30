"""add default_settings to indexer_site_config

Revision ID: ee2445e35880
Revises: c4d5e6f7a8b9
Create Date: 2026-06-30 06:59:06.210292

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

revision: str = "ee2445e35880"
down_revision: Union[str, None] = "c4d5e6f7a8b9"
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

    if _table_exists(conn, table_name) and not _column_exists(conn, table_name, "DEFAULT_SETTINGS"):
        op.add_column(
            table_name,
            sa.Column("DEFAULT_SETTINGS", sa.Text(), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    table_name = "INDEXER_SITE_CONFIG"

    if _table_exists(conn, table_name) and _column_exists(conn, table_name, "DEFAULT_SETTINGS"):
        op.drop_column(table_name, "DEFAULT_SETTINGS")
