"""add series key to media tables

Revision ID: 9217b6230331
Revises: ed7599911b91
Create Date: 2026-11-05 13:31:42.979867

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "9217b6230331"
down_revision = "ed7599911b91"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("DOWNLOAD_HISTORY", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_DOWNLOAD_HISTORY_SERIES_KEY", "DOWNLOAD_HISTORY", ["SERIES_KEY"])
    op.add_column("TRANSFER_HISTORY", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_TRANSFER_HISTORY_SERIES_KEY", "TRANSFER_HISTORY", ["SERIES_KEY"])
    op.add_column("MEDIA_LIFECYCLE", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_MEDIA_LIFECYCLE_SERIES_KEY", "MEDIA_LIFECYCLE", ["SERIES_KEY"])
    op.add_column("MEDIA_LIFECYCLE_EVENT", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_MEDIA_LIFECYCLE_EVENT_SERIES_KEY", "MEDIA_LIFECYCLE_EVENT", ["SERIES_KEY"])
    op.add_column("SUBSCRIBE_HISTORY", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_SUBSCRIBE_HISTORY_SERIES_KEY", "SUBSCRIBE_HISTORY", ["SERIES_KEY"])
    op.add_column("SUBSCRIBE_TORRENTS", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_SUBSCRIBE_TORRENTS_SERIES_KEY", "SUBSCRIBE_TORRENTS", ["SERIES_KEY"])


def downgrade() -> None:
    op.drop_index("ix_SUBSCRIBE_TORRENTS_SERIES_KEY", table_name="SUBSCRIBE_TORRENTS")
    op.drop_column("SUBSCRIBE_TORRENTS", "SERIES_KEY")
    op.drop_index("ix_SUBSCRIBE_HISTORY_SERIES_KEY", table_name="SUBSCRIBE_HISTORY")
    op.drop_column("SUBSCRIBE_HISTORY", "SERIES_KEY")
    op.drop_index("ix_MEDIA_LIFECYCLE_EVENT_SERIES_KEY", table_name="MEDIA_LIFECYCLE_EVENT")
    op.drop_column("MEDIA_LIFECYCLE_EVENT", "SERIES_KEY")
    op.drop_index("ix_MEDIA_LIFECYCLE_SERIES_KEY", table_name="MEDIA_LIFECYCLE")
    op.drop_column("MEDIA_LIFECYCLE", "SERIES_KEY")
    op.drop_index("ix_TRANSFER_HISTORY_SERIES_KEY", table_name="TRANSFER_HISTORY")
    op.drop_column("TRANSFER_HISTORY", "SERIES_KEY")
    op.drop_index("ix_DOWNLOAD_HISTORY_SERIES_KEY", table_name="DOWNLOAD_HISTORY")
    op.drop_column("DOWNLOAD_HISTORY", "SERIES_KEY")
