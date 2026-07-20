"""make torrent remove task note nullable

Revision ID: w1x2y3z4a5b6
Revises: hulmg190gx4k
Create Date: 2026-07-20T13:55:41.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "w1x2y3z4a5b6"
down_revision = "hulmg190gx4k"
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
    if not has_table("TORRENT_REMOVE_TASK"):
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("TORRENT_REMOVE_TASK") as batch_op:
            batch_op.alter_column("NOTE", existing_type=sa.Text(), nullable=True)
    else:
        op.alter_column("TORRENT_REMOVE_TASK", "NOTE", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    if not has_table("TORRENT_REMOVE_TASK"):
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("TORRENT_REMOVE_TASK") as batch_op:
            batch_op.alter_column("NOTE", existing_type=sa.Text(), nullable=False)
    else:
        op.alter_column("TORRENT_REMOVE_TASK", "NOTE", existing_type=sa.Text(), nullable=False)
