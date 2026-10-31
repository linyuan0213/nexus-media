"""add category rule json

Revision ID: 0beb76e4b6d2
Revises: 950970b455a8
Create Date: 2026-10-31 09:14:30.463815

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "0beb76e4b6d2"
down_revision = "950970b455a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("CONFIG_CATEGORY_RULE") as batch:
        batch.add_column(sa.Column("RULE_JSON", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("CONFIG_CATEGORY_RULE") as batch:
        batch.drop_column("RULE_JSON")
