"""add FILTER_FREE to subscribe

Revision ID: b9fylp3wdfho
Revises: 1ee439ce9b6d
Create Date: 2026-07-07T01:00:43.000556

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b9fylp3wdfho"
down_revision = "e5efa40afddb"
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def has_table(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    for table in ("SUBSCRIBE_MOVIES", "SUBSCRIBE_TVS"):
        if has_table(table) and not has_column(table, "FILTER_FREE"):
            op.add_column(table, sa.Column("FILTER_FREE", sa.Integer(), nullable=True))


def downgrade() -> None:
    for table in ("SUBSCRIBE_MOVIES", "SUBSCRIBE_TVS"):
        if has_table(table) and has_column(table, "FILTER_FREE"):
            op.drop_column(table, "FILTER_FREE")
