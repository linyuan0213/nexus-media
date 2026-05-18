"""rename_only_nexus_media_columns

Revision ID: b2c3d4e5f6a7
Revises: a3b4c5d6e7f8
Create Date: 2026-05-18 04:00:00.000000

"""

from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("DOWNLOADER", "ONLY_NASTOOL", new_column_name="ONLY_NEXUS_MEDIA")
    op.alter_column("TORRENT_REMOVE_TASK", "ONLYNASTOOL", new_column_name="ONLY_NEXUS_MEDIA")


def downgrade():
    op.alter_column("DOWNLOADER", "ONLY_NEXUS_MEDIA", new_column_name="ONLY_NASTOOL")
    op.alter_column("TORRENT_REMOVE_TASK", "ONLY_NEXUS_MEDIA", new_column_name="ONLYNASTOOL")
