"""make download_setting note nullable

Revision ID: oxrva77k36j6
Revises: c7a1b2c3d4e6
Create Date: 2026-07-11T04:26:23.392790

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "oxrva77k36j6"
down_revision = "c7a1b2c3d4e6"
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
    if not has_table("DOWNLOAD_SETTING"):
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("DOWNLOAD_SETTING") as batch_op:
            batch_op.alter_column("NOTE", existing_type=sa.Text(), nullable=True)
    else:
        op.alter_column("DOWNLOAD_SETTING", "NOTE", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    if not has_table("DOWNLOAD_SETTING"):
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("DOWNLOAD_SETTING") as batch_op:
            batch_op.alter_column("NOTE", existing_type=sa.Text(), nullable=False)
    else:
        op.alter_column("DOWNLOAD_SETTING", "NOTE", existing_type=sa.Text(), nullable=False)
