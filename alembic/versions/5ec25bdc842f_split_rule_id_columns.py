"""split rule id columns

Revision ID: 5ec25bdc842f
Revises: 1dda6a1d4044
Create Date: 2026-07-01 14:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "5ec25bdc842f"
down_revision: str | None = "1dda6a1d4044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("SITE_BRUSH_TASK", sa.Column("RSS_RULE_ID", sa.Integer(), nullable=True))
    op.add_column("SITE_BRUSH_TASK", sa.Column("REMOVE_RULE_ID", sa.Integer(), nullable=True))
    op.add_column("SITE_BRUSH_TASK", sa.Column("STOP_RULE_ID", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_site_brush_task_rss_rule_id",
        "SITE_BRUSH_TASK",
        "SITE_BRUSH_RULE",
        ["RSS_RULE_ID"],
        ["ID"],
    )
    op.create_foreign_key(
        "fk_site_brush_task_remove_rule_id",
        "SITE_BRUSH_TASK",
        "SITE_BRUSH_RULE",
        ["REMOVE_RULE_ID"],
        ["ID"],
    )
    op.create_foreign_key(
        "fk_site_brush_task_stop_rule_id",
        "SITE_BRUSH_TASK",
        "SITE_BRUSH_RULE",
        ["STOP_RULE_ID"],
        ["ID"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_site_brush_task_stop_rule_id", "SITE_BRUSH_TASK", type_="foreignkey")
    op.drop_constraint("fk_site_brush_task_remove_rule_id", "SITE_BRUSH_TASK", type_="foreignkey")
    op.drop_constraint("fk_site_brush_task_rss_rule_id", "SITE_BRUSH_TASK", type_="foreignkey")
    op.drop_column("SITE_BRUSH_TASK", "STOP_RULE_ID")
    op.drop_column("SITE_BRUSH_TASK", "REMOVE_RULE_ID")
    op.drop_column("SITE_BRUSH_TASK", "RSS_RULE_ID")
