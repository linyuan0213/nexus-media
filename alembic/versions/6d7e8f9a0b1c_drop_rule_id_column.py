"""drop rule id column

Revision ID: 6d7e8f9a0b1c
Revises: 5ec25bdc842f
Create Date: 2026-07-01 14:55:00.000000

"""

from collections.abc import Sequence

from alembic import op

revision: str = "6d7e8f9a0b1c"
down_revision: str | None = "5ec25bdc842f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("SITE_BRUSH_TASK_ibfk_1", "SITE_BRUSH_TASK", type_="foreignkey")
    op.drop_column("SITE_BRUSH_TASK", "RULE_ID")


def downgrade() -> None:
    pass
