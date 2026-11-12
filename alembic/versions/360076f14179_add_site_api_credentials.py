"""add site api credentials

Revision ID: 360076f14179
Revises: e9286eb1682f
Create Date: 2026-11-12 08:01:44.319386

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "360076f14179"
down_revision = "e9286eb1682f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "CONFIG_SITE_API_CREDENTIAL",
        sa.Column("ID", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("SITE_ID", sa.Integer(), nullable=False),
        sa.Column("PROFILE", sa.String(length=64), nullable=False),
        sa.Column("DATA", sa.Text(), nullable=False),
        sa.Column("UPDATED_AT", sa.String(length=32), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["SITE_ID"], ["CONFIG_SITE.ID"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ID"),
        sa.UniqueConstraint("SITE_ID", "PROFILE", name="UN_CONFIG_SITE_API_CREDENTIAL"),
    )
    op.create_index(
        "ix_CONFIG_SITE_API_CREDENTIAL_SITE_ID",
        "CONFIG_SITE_API_CREDENTIAL",
        ["SITE_ID"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_CONFIG_SITE_API_CREDENTIAL_SITE_ID", table_name="CONFIG_SITE_API_CREDENTIAL")
    op.drop_table("CONFIG_SITE_API_CREDENTIAL")
