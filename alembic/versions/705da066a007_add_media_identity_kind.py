"""add media identity kind

Revision ID: 705da066a007
Revises: 552317c078ed
Create Date: 2026-11-07 10:20:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "705da066a007"
down_revision = "552317c078ed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "MEDIA_IDENTITY",
        sa.Column("MEDIA_KIND", sa.String(16), nullable=False, server_default="unknown"),
    )
    op.execute(
        """
        UPDATE MEDIA_IDENTITY
        SET MEDIA_KIND = CASE
            WHEN MEDIA_TYPE = 'movie' THEN 'movie'
            WHEN MEDIA_TYPE IN ('tv', 'anime') THEN 'episodic'
            ELSE 'unknown'
        END
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("MEDIA_IDENTITY") as batch:
            batch.drop_column("MEDIA_KIND")
        return
    op.drop_column("MEDIA_IDENTITY", "MEDIA_KIND")
