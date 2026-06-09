"""add_dst_backend_to_transfer_history

Revision ID: e5f6a7b8c9d0
Revises: c1d2e3f4a5b6
Create Date: 2026-05-22 09:58:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column

revision = "e5f6a7b8c9d0"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not has_column("TRANSFER_HISTORY", "DST_BACKEND"):
        op.add_column("TRANSFER_HISTORY", Column("DST_BACKEND", sa.String(64), nullable=True))


def downgrade():
    if has_column("TRANSFER_HISTORY", "DST_BACKEND"):
        op.drop_column("TRANSFER_HISTORY", "DST_BACKEND")
