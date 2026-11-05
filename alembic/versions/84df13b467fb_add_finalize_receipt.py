"""add finalize receipt

Revision ID: 84df13b467fb
Revises: 5946e2c6be6d
Create Date: 2026-11-05 09:41:41.832246

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "84df13b467fb"
down_revision = "5946e2c6be6d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "FINALIZE_RECEIPT",
        sa.Column("RECEIPT_KEY", sa.String(length=512), nullable=False),
        sa.Column("CREATED_AT", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("RECEIPT_KEY"),
    )


def downgrade() -> None:
    op.drop_table("FINALIZE_RECEIPT")
