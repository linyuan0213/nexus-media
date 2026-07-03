"""add_task_limits_and_rules

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-07-03 03:10:00

Add DAILY_DELETE_LIMIT, MAX_SEEDING task config + new remove rule fields.
"""

import sqlalchemy as sa

from alembic import op

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def has_table(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return inspector.has_table(table_name)


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if not has_table("SITE_BRUSH_TASK"):
        return
    for col in ["DAILY_DELETE_LIMIT", "MAX_SEEDING"]:
        if not has_column("SITE_BRUSH_TASK", col):
            op.add_column("SITE_BRUSH_TASK", sa.Column(col, sa.String(10), nullable=True))


def downgrade() -> None:
    for col in ["DAILY_DELETE_LIMIT", "MAX_SEEDING"]:
        if has_column("SITE_BRUSH_TASK", col):
            op.drop_column("SITE_BRUSH_TASK", col)
