"""make system dict value text

Revision ID: hulmg190gx4k
Revises: 1ee439ce9b6d
Create Date: 2026-07-16T05:34:07.379940

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "hulmg190gx4k"
down_revision = "oxrva77k36j6"
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
    if not has_table("SYSTEM_DICT"):
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("SYSTEM_DICT") as batch_op:
            batch_op.alter_column("VALUE", type_=sa.Text(), existing_type=sa.String(255))
    else:
        op.alter_column("SYSTEM_DICT", "VALUE", type_=sa.Text(), existing_type=sa.String(255))


def downgrade() -> None:
    if not has_table("SYSTEM_DICT"):
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("SYSTEM_DICT") as batch_op:
            batch_op.alter_column("VALUE", type_=sa.String(255), existing_type=sa.Text())
    else:
        op.alter_column("SYSTEM_DICT", "VALUE", type_=sa.String(255), existing_type=sa.Text())
