"""site_user_info_stats_server_defaults

Revision ID: f6f7a8b9c0d1
Revises: e6f7a8b9c0d1
Create Date: 2026-06-23 21:02:00.000000

"""

import sqlalchemy as sa
from sqlalchemy import inspect, text

from alembic import op

revision: str = "f6f7a8b9c0d1"
down_revision: str = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = {c["name"].upper() for c in inspect(conn).get_columns(table)}
    return column.upper() in cols


_COLUMN_DEFAULTS = {
    "SITE_USER_INFO_STATS": {
        "USERNAME": (sa.String(255), text("''")),
        "JOIN_AT": (sa.String(255), text("''")),
        "UPDATE_AT": (sa.String(255), text("''")),
        "UPLOAD": (sa.BigInteger, text("0")),
        "DOWNLOAD": (sa.BigInteger, text("0")),
        "RATIO": (sa.Float, text("0.0")),
        "SEEDING": (sa.Integer, text("0")),
        "LEECHING": (sa.Integer, text("0")),
        "SEEDING_SIZE": (sa.BigInteger, text("0")),
        "BONUS": (sa.Float, text("0.0")),
        "MSG_UNREAD": (sa.Integer, text("0")),
        "EXT_INFO": (sa.String(255), text("''")),
    },
    "SITE_STATISTICS_HISTORY": {
        "UPLOAD": (sa.BigInteger, text("0")),
        "DOWNLOAD": (sa.BigInteger, text("0")),
        "RATIO": (sa.Float, text("0.0")),
    },
}


def upgrade() -> None:
    for table, columns in _COLUMN_DEFAULTS.items():
        if not inspect(op.get_bind()).has_table(table):
            continue
        for col, (col_type, col_default) in columns.items():
            if not _column_exists(table, col):
                continue
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column(
                    col,
                    existing_type=col_type,
                    server_default=col_default,
                    existing_nullable=True,
                )


def downgrade() -> None:
    for table, columns in _COLUMN_DEFAULTS.items():
        if not inspect(op.get_bind()).has_table(table):
            continue
        for col, (col_type, _col_default) in columns.items():
            if not _column_exists(table, col):
                continue
            with op.batch_alter_table(table, schema=None) as batch_op:
                batch_op.alter_column(
                    col,
                    existing_type=col_type,
                    server_default=None,
                    existing_nullable=True,
                )
