"""add_hr_limit

Revision ID: f0a1b2c3d4e5
Revises: e8f9a0b1c2d3
Create Date: 2026-07-03 03:35:00

Add HR_LIMIT column to SITE_BRUSH_TASK.
"""

import sqlalchemy as sa

from alembic import op

revision = "f0a1b2c3d4e5"
down_revision = "e8f9a0b1c2d3"
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
    if has_table("SITE_BRUSH_TASK") and not has_column("SITE_BRUSH_TASK", "HR_LIMIT"):
        op.add_column("SITE_BRUSH_TASK", sa.Column("HR_LIMIT", sa.String(10), nullable=True))


def downgrade() -> None:
    if has_column("SITE_BRUSH_TASK", "HR_LIMIT"):
        op.drop_column("SITE_BRUSH_TASK", "HR_LIMIT")
