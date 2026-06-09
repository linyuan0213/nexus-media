"""add_storage_backend_and_sync_fields

Revision ID: f1a2b3c4d5e6
Revises: 4a25eb3cc474
Create Date: 2026-05-17 01:26:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column

revision = "f1a2b3c4d5e6"
down_revision = "4a25eb3cc474"
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
    if not has_column("CONFIG_SYNC_PATHS", "OPERATION"):
        op.add_column("CONFIG_SYNC_PATHS", Column("OPERATION", sa.String(50), nullable=True))
    if not has_column("CONFIG_SYNC_PATHS", "SRC_BACKEND"):
        op.add_column("CONFIG_SYNC_PATHS", Column("SRC_BACKEND", sa.String(64), server_default="local"))
    if not has_column("CONFIG_SYNC_PATHS", "DST_BACKEND"):
        op.add_column("CONFIG_SYNC_PATHS", Column("DST_BACKEND", sa.String(64), server_default="local"))

    op.execute("""
        UPDATE CONFIG_SYNC_PATHS SET OPERATION = CASE
            WHEN MODE IN ('copy', 'rclonecopy', 'miniocopy') THEN 'copy'
            WHEN MODE IN ('move', 'rclone', 'minio') THEN 'move'
            WHEN MODE = 'link' THEN 'link'
            WHEN MODE = 'softlink' THEN 'softlink'
            ELSE 'copy'
        END
        WHERE OPERATION IS NULL OR OPERATION = ''
    """)


def downgrade():
    if has_column("CONFIG_SYNC_PATHS", "OPERATION"):
        op.drop_column("CONFIG_SYNC_PATHS", "OPERATION")
    if has_column("CONFIG_SYNC_PATHS", "SRC_BACKEND"):
        op.drop_column("CONFIG_SYNC_PATHS", "SRC_BACKEND")
    if has_column("CONFIG_SYNC_PATHS", "DST_BACKEND"):
        op.drop_column("CONFIG_SYNC_PATHS", "DST_BACKEND")
