"""add_page_url_to_site_brush_torrents

Revision ID: d4efa40afddb
Revises: c3efa40afddb
Create Date: 2026-07-05 04:01:00

Add PAGE_URL column to SITE_BRUSH_TORRENTS to store torrent detail page URL.
"""

import sqlalchemy as sa

from alembic import op

revision = "d4efa40afddb"
down_revision = "c3efa40afddb"
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
    if not has_column("SITE_BRUSH_TORRENTS", "PAGE_URL"):
        op.add_column(
            "SITE_BRUSH_TORRENTS",
            sa.Column("PAGE_URL", sa.String(1024), server_default="", default=""),
        )


def downgrade():
    if has_column("SITE_BRUSH_TORRENTS", "PAGE_URL"):
        op.drop_column("SITE_BRUSH_TORRENTS", "PAGE_URL")
