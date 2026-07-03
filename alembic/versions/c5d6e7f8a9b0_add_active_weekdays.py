"""add_active_weekdays

Revision ID: c5d6e7f8a9b0
Revises: 77f7a8b9c0d1
Create Date: 2026-07-03 01:15:00

Add ACTIVE_WEEKDAYS column to SITE_BRUSH_TASK for day-of-week scheduling.
"""

import sqlalchemy as sa

from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "77f7a8b9c0d1"
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
    if not has_column("SITE_BRUSH_TASK", "ACTIVE_WEEKDAYS"):
        op.add_column("SITE_BRUSH_TASK", sa.Column("ACTIVE_WEEKDAYS", sa.String(255), nullable=True))


def downgrade() -> None:
    if has_column("SITE_BRUSH_TASK", "ACTIVE_WEEKDAYS"):
        op.drop_column("SITE_BRUSH_TASK", "ACTIVE_WEEKDAYS")
