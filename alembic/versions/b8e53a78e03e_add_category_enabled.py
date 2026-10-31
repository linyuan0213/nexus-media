"""add category enabled

Revision ID: b8e53a78e03e
Revises: 0beb76e4b6d2
Create Date: 2026-10-31 10:22:42.656668

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "b8e53a78e03e"
down_revision = "0beb76e4b6d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("CONFIG_CATEGORY") as batch:
        batch.add_column(sa.Column("ENABLED", sa.Integer(), nullable=False, server_default="1"))


def downgrade() -> None:
    with op.batch_alter_table("CONFIG_CATEGORY") as batch:
        batch.drop_column("ENABLED")
