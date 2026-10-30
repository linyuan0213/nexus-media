"""add media layout

Revision ID: 950970b455a8
Revises: 007e81318aee
Create Date: 2026-10-30 22:30:47.584209

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "950970b455a8"
down_revision = "007e81318aee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("CONFIG_MEDIA") as batch:
        batch.add_column(sa.Column("MOVIE_LAYOUT", sa.String(20), nullable=False, server_default="category"))
        batch.add_column(sa.Column("TV_LAYOUT", sa.String(20), nullable=False, server_default="category"))
        batch.add_column(sa.Column("ANIME_LAYOUT", sa.String(20), nullable=False, server_default="flat"))


def downgrade() -> None:
    with op.batch_alter_table("CONFIG_MEDIA") as batch:
        batch.drop_column("ANIME_LAYOUT")
        batch.drop_column("TV_LAYOUT")
        batch.drop_column("MOVIE_LAYOUT")
