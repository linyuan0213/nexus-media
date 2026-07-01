"""add type to brush rule

Revision ID: 1dda6a1d4044
Revises: f65506008fd7
Create Date: 2026-07-01 14:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1dda6a1d4044"
down_revision: str | None = "ee2445e35880"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "SITE_BRUSH_RULE",
        sa.Column("TYPE", sa.String(10), nullable=False, server_default="all"),
    )


def downgrade() -> None:
    op.drop_column("SITE_BRUSH_RULE", "TYPE")
