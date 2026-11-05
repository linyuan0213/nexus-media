"""add subscribe retry backoff

Revision ID: 037e7bbf796b
Revises: 3a6abdf71b57
Create Date: 2026-11-05 15:48:37.663438

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "037e7bbf796b"
down_revision = "3a6abdf71b57"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("SUBSCRIBE_MOVIES", "SUBSCRIBE_TVS"):
        op.add_column(table, sa.Column("RETRY_COUNT", sa.Integer(), nullable=False, server_default="0"))
        op.add_column(table, sa.Column("NEXT_RETRY_AT", sa.String(length=255), nullable=True))


def downgrade() -> None:
    for table in ("SUBSCRIBE_TVS", "SUBSCRIBE_MOVIES"):
        op.drop_column(table, "NEXT_RETRY_AT")
        op.drop_column(table, "RETRY_COUNT")
