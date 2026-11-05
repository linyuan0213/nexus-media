"""add media series alias

Revision ID: ed7599911b91
Revises: 84df13b467fb
Create Date: 2026-11-05 13:21:30.154990

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "ed7599911b91"
down_revision = "84df13b467fb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "MEDIA_SERIES",
        sa.Column("SERIES_KEY", sa.String(length=64), nullable=False),
        sa.Column("PRIMARY_PROVIDER", sa.String(length=64), nullable=True),
        sa.Column("PRIMARY_EXTERNAL_ID", sa.String(length=255), nullable=True),
        sa.Column("TITLE", sa.String(length=255), nullable=False),
        sa.Column("ORIGINAL_TITLE", sa.String(length=255), nullable=True),
        sa.Column("YEAR", sa.String(length=10), nullable=True),
        sa.Column("TOTAL_SEASONS", sa.Integer(), nullable=False),
        sa.Column("CREATED_AT", sa.String(length=20), nullable=True),
        sa.Column("UPDATED_AT", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("SERIES_KEY"),
    )
    op.create_table(
        "MEDIA_SERIES_SEASON",
        sa.Column("SERIES_KEY", sa.String(length=64), nullable=False),
        sa.Column("SEASON_NUMBER", sa.Integer(), nullable=False),
        sa.Column("TITLE", sa.String(length=255), nullable=True),
        sa.Column("YEAR", sa.String(length=10), nullable=True),
        sa.Column("TOTAL_EPISODES", sa.Integer(), nullable=True),
        sa.Column("EPISODE_OFFSET", sa.Integer(), nullable=False),
        sa.Column("PRIMARY_PROVIDER", sa.String(length=64), nullable=True),
        sa.Column("PRIMARY_EXTERNAL_ID", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("SERIES_KEY", "SEASON_NUMBER"),
    )
    op.create_table(
        "MEDIA_SERIES_ALIAS",
        sa.Column("PROVIDER", sa.String(length=64), nullable=False),
        sa.Column("EXTERNAL_ID", sa.String(length=255), nullable=False),
        sa.Column("SCOPE", sa.String(length=64), nullable=False),
        sa.Column("SEASON_NUMBER", sa.Integer(), nullable=False),
        sa.Column("SERIES_KEY", sa.String(length=64), nullable=False),
        sa.Column("CONFIDENCE", sa.Integer(), nullable=False),
        sa.Column("MAPPING_SOURCE", sa.String(length=32), nullable=False),
        sa.Column("CREATED_AT", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE"),
        sa.UniqueConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE", name="uq_series_alias_provider_ref"),
    )
    op.create_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", "MEDIA_SERIES_ALIAS", ["SERIES_KEY"])
    op.add_column("SUBSCRIBE_TVS", sa.Column("SERIES_KEY", sa.String(length=64), nullable=True))
    op.create_index("ix_SUBSCRIBE_TVS_SERIES_KEY", "SUBSCRIBE_TVS", ["SERIES_KEY"])


def downgrade() -> None:
    op.drop_index("ix_SUBSCRIBE_TVS_SERIES_KEY", table_name="SUBSCRIBE_TVS")
    op.drop_column("SUBSCRIBE_TVS", "SERIES_KEY")
    op.drop_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", table_name="MEDIA_SERIES_ALIAS")
    op.drop_table("MEDIA_SERIES_ALIAS")
    op.drop_table("MEDIA_SERIES_SEASON")
    op.drop_table("MEDIA_SERIES")
