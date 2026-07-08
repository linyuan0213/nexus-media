"""add IS_BUILTIN to RBAC_MENUS

Revision ID: c7a1b2c3d4e6
Revises: b9fylp3wdfho
Create Date: 2026-07-08T08:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "c7a1b2c3d4e6"
down_revision = "b9fylp3wdfho"
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
    if has_table("RBAC_MENUS") and not has_column("RBAC_MENUS", "IS_BUILTIN"):
        op.add_column(
            "RBAC_MENUS",
            sa.Column("IS_BUILTIN", sa.Integer(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    if has_table("RBAC_MENUS") and has_column("RBAC_MENUS", "IS_BUILTIN"):
        op.drop_column("RBAC_MENUS", "IS_BUILTIN")
