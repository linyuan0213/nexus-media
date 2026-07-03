"""add_phase_switches

Revision ID: d7e8f9a0b1c2
Revises: c5d6e7f8a9b0
Create Date: 2026-07-03 01:40:00

Add DOWNLOAD_SWITCH, REMOVE_SWITCH, STOP_SWITCH columns to SITE_BRUSH_TASK
for independent phase control.
"""

import sqlalchemy as sa

from alembic import op

revision = "d7e8f9a0b1c2"
down_revision = "c5d6e7f8a9b0"
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
    for col in ["DOWNLOAD_SWITCH", "REMOVE_SWITCH", "STOP_SWITCH"]:
        if not has_column("SITE_BRUSH_TASK", col):
            op.add_column("SITE_BRUSH_TASK", sa.Column(col, sa.String(1), nullable=True))


def downgrade() -> None:
    for col in ["DOWNLOAD_SWITCH", "REMOVE_SWITCH", "STOP_SWITCH"]:
        if has_column("SITE_BRUSH_TASK", col):
            op.drop_column("SITE_BRUSH_TASK", col)
