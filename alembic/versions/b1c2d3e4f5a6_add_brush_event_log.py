"""add_brush_event_log

Revision ID: b1c2d3e4f5a6
Revises: f0a1b2c3d4e5
Create Date: 2026-07-03 04:00:00

Add BRUSH_EVENT_LOG table for recording brush delete/stop events.
"""

import sqlalchemy as sa

from alembic import op

revision = "b1c2d3e4f5a6"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def has_table(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return inspector.has_table(table_name)


def upgrade() -> None:
    if not has_table("BRUSH_EVENT_LOG"):
        op.create_table(
            "BRUSH_EVENT_LOG",
            sa.Column("ID", sa.Integer(), autoincrement=True, primary_key=True),
            sa.Column("TASK_ID", sa.Integer(), nullable=False),
            sa.Column("TASK_NAME", sa.String(255), default=""),
            sa.Column("TORRENT_NAME", sa.String(512), default=""),
            sa.Column("DOWNLOAD_ID", sa.String(255), default=""),
            sa.Column("ACTION", sa.String(16), nullable=False),
            sa.Column("REASON", sa.String(255), default=""),
            sa.Column("DOWNLOADER_NAME", sa.String(255), default=""),
            sa.Column("SITE_NAME", sa.String(255), default=""),
            sa.Column("CREATED_AT", sa.String(32), default=""),
        )
        op.create_index("INDX_BRUSH_EVENT_LOG_TASK_ID", "BRUSH_EVENT_LOG", ["TASK_ID"])


def downgrade() -> None:
    if has_table("BRUSH_EVENT_LOG"):
        op.drop_index("INDX_BRUSH_EVENT_LOG_TASK_ID", table_name="BRUSH_EVENT_LOG")
        op.drop_table("BRUSH_EVENT_LOG")
