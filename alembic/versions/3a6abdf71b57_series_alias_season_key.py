"""series alias season key

Revision ID: 3a6abdf71b57
Revises: 9217b6230331
Create Date: 2026-11-05 13:32:14.928480

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "3a6abdf71b57"
down_revision = "9217b6230331"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.rename_table("MEDIA_SERIES_ALIAS", "MEDIA_SERIES_ALIAS_OLD")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # PostgreSQL 的约束/索引名在 schema 内全局唯一，旧表改名后仍占用原名。
        op.drop_constraint("uq_series_alias_provider_ref", "MEDIA_SERIES_ALIAS_OLD", type_="unique")
        op.drop_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", table_name="MEDIA_SERIES_ALIAS_OLD")
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
        sa.PrimaryKeyConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE", "SEASON_NUMBER"),
        sa.UniqueConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE", "SEASON_NUMBER", name="uq_series_alias_provider_ref"),
    )
    op.create_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", "MEDIA_SERIES_ALIAS", ["SERIES_KEY"])
    op.execute(
        "INSERT INTO MEDIA_SERIES_ALIAS "
        "(PROVIDER, EXTERNAL_ID, SCOPE, SEASON_NUMBER, SERIES_KEY, CONFIDENCE, MAPPING_SOURCE, CREATED_AT) "
        "SELECT PROVIDER, EXTERNAL_ID, SCOPE, SEASON_NUMBER, SERIES_KEY, CONFIDENCE, MAPPING_SOURCE, CREATED_AT "
        "FROM MEDIA_SERIES_ALIAS_OLD"
    )
    op.drop_table("MEDIA_SERIES_ALIAS_OLD")


def downgrade() -> None:
    op.rename_table("MEDIA_SERIES_ALIAS", "MEDIA_SERIES_ALIAS_OLD")
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
    )
    op.execute(
        "INSERT INTO MEDIA_SERIES_ALIAS "
        "(PROVIDER, EXTERNAL_ID, SCOPE, SEASON_NUMBER, SERIES_KEY, CONFIDENCE, MAPPING_SOURCE, CREATED_AT) "
        "SELECT PROVIDER, EXTERNAL_ID, SCOPE, SEASON_NUMBER, SERIES_KEY, CONFIDENCE, MAPPING_SOURCE, CREATED_AT "
        "FROM MEDIA_SERIES_ALIAS_OLD"
    )
    op.drop_table("MEDIA_SERIES_ALIAS_OLD")
