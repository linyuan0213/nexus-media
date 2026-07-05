"""add_torrent_url_to_brush_event_log

Revision ID: c3efa40afddb
Revises: b1c2d3e4f5a6
Create Date: 2026-07-05 04:00:00

Add TORRENT_URL column to BRUSH_EVENT_LOG for linking to torrent detail pages.
"""

import sqlalchemy as sa

from alembic import op

revision = "c3efa40afddb"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not has_column("BRUSH_EVENT_LOG", "TORRENT_URL"):
        op.add_column(
            "BRUSH_EVENT_LOG",
            sa.Column("TORRENT_URL", sa.String(512), server_default="", default=""),
        )


def downgrade():
    if has_column("BRUSH_EVENT_LOG", "TORRENT_URL"):
        op.drop_column("BRUSH_EVENT_LOG", "TORRENT_URL")
