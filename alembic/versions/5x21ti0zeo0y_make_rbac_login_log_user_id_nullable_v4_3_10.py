"""make rbac login log user_id nullable

Revision ID: 5x21ti0zeo0y
Revises: 1ee439ce9b6d
Create Date: 2026-07-21T08:46:07.633854

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "5x21ti0zeo0y"
down_revision = "w1x2y3z4a5b6"
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
    with op.batch_alter_table("RBAC_USER_LOGIN_LOGS", schema=None) as batch_op:
        batch_op.alter_column(
            "USER_ID",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("RBAC_USER_LOGIN_LOGS", schema=None) as batch_op:
        batch_op.alter_column(
            "USER_ID",
            existing_type=sa.Integer(),
            nullable=False,
        )
