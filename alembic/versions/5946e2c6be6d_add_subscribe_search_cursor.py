"""add subscribe search cursor

Revision ID: 5946e2c6be6d
Revises: 390cdc4e20cc
Create Date: 2026-11-05 09:39:47.764774

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "5946e2c6be6d"
down_revision = "390cdc4e20cc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "SUBSCRIBE_SEARCH_CURSOR",
        sa.Column("KIND", sa.String(length=32), nullable=False),
        sa.Column("POSITION", sa.Integer(), nullable=False),
        sa.Column("UPDATED_AT", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("KIND"),
    )


def downgrade() -> None:
    op.drop_table("SUBSCRIBE_SEARCH_CURSOR")
