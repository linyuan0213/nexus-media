"""add_media_backend_fields

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-05-17 01:26:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column

revision = "f2a3b4c5d6e7"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not has_column("CONFIG_MEDIA", "MOVIE_BACKEND"):
        op.add_column("CONFIG_MEDIA", Column("MOVIE_BACKEND", sa.Text(), nullable=True))
    if not has_column("CONFIG_MEDIA", "TV_BACKEND"):
        op.add_column("CONFIG_MEDIA", Column("TV_BACKEND", sa.Text(), nullable=True))
    if not has_column("CONFIG_MEDIA", "ANIME_BACKEND"):
        op.add_column("CONFIG_MEDIA", Column("ANIME_BACKEND", sa.Text(), nullable=True))
    if not has_column("CONFIG_MEDIA", "UNKNOWN_BACKEND"):
        op.add_column("CONFIG_MEDIA", Column("UNKNOWN_BACKEND", sa.Text(), nullable=True))


def downgrade():
    if has_column("CONFIG_MEDIA", "MOVIE_BACKEND"):
        op.drop_column("CONFIG_MEDIA", "MOVIE_BACKEND")
    if has_column("CONFIG_MEDIA", "TV_BACKEND"):
        op.drop_column("CONFIG_MEDIA", "TV_BACKEND")
    if has_column("CONFIG_MEDIA", "ANIME_BACKEND"):
        op.drop_column("CONFIG_MEDIA", "ANIME_BACKEND")
    if has_column("CONFIG_MEDIA", "UNKNOWN_BACKEND"):
        op.drop_column("CONFIG_MEDIA", "UNKNOWN_BACKEND")
