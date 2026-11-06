"""add media identity aliases

Revision ID: 9d0379c17274
Revises: acee483709ff
Create Date: 2026-11-06 21:09:28.619676

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "9d0379c17274"
down_revision = "acee483709ff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("MEDIA_IDENTITY", sa.Column("ALIASES", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("MEDIA_IDENTITY", "ALIASES")
