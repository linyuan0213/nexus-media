"""add subscribe state updated at

Revision ID: 390cdc4e20cc
Revises: 0b3efe0a09cb
Create Date: 2026-11-05 09:38:19.038632

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "390cdc4e20cc"
down_revision = "0b3efe0a09cb"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("SUBSCRIBE_MOVIES", sa.Column("STATE_UPDATED_AT", sa.String(length=255), nullable=True))
    op.create_index("IX_SUBSCRIBE_MOVIES_STATE_UPDATED_AT", "SUBSCRIBE_MOVIES", ["STATE_UPDATED_AT"])
    op.add_column("SUBSCRIBE_TVS", sa.Column("STATE_UPDATED_AT", sa.String(length=255), nullable=True))
    op.create_index("IX_SUBSCRIBE_TVS_STATE_UPDATED_AT", "SUBSCRIBE_TVS", ["STATE_UPDATED_AT"])


def downgrade() -> None:
    op.drop_index("IX_SUBSCRIBE_TVS_STATE_UPDATED_AT", table_name="SUBSCRIBE_TVS")
    op.drop_column("SUBSCRIBE_TVS", "STATE_UPDATED_AT")
    op.drop_index("IX_SUBSCRIBE_MOVIES_STATE_UPDATED_AT", table_name="SUBSCRIBE_MOVIES")
    op.drop_column("SUBSCRIBE_MOVIES", "STATE_UPDATED_AT")
