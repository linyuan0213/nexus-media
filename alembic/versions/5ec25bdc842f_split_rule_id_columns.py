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


def has_table(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return inspector.has_table(table_name)


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if not inspector.has_table(table_name):
        return False
    columns = inspector.get_columns(table_name)
    return any(col["name"] == column_name for col in columns)


def upgrade() -> None:
    if has_table("SITE_BRUSH_TASK") and not has_column("SITE_BRUSH_TASK", "RSS_RULE_ID"):
        op.add_column("SITE_BRUSH_TASK", sa.Column("RSS_RULE_ID", sa.Integer(), nullable=True))
    if has_table("SITE_BRUSH_TASK") and not has_column("SITE_BRUSH_TASK", "REMOVE_RULE_ID"):
        op.add_column("SITE_BRUSH_TASK", sa.Column("REMOVE_RULE_ID", sa.Integer(), nullable=True))
    if has_table("SITE_BRUSH_TASK") and not has_column("SITE_BRUSH_TASK", "STOP_RULE_ID"):
        op.add_column("SITE_BRUSH_TASK", sa.Column("STOP_RULE_ID", sa.Integer(), nullable=True))
    if not has_table("SITE_BRUSH_TASK"):
        return
    existing = {
        tuple(fk.get("constrained_columns") or [])
        for fk in sa.inspect(op.get_bind()).get_foreign_keys("SITE_BRUSH_TASK")
    }
    fks = [
        ("fk_site_brush_task_rss_rule_id", ["RSS_RULE_ID"]),
        ("fk_site_brush_task_remove_rule_id", ["REMOVE_RULE_ID"]),
        ("fk_site_brush_task_stop_rule_id", ["STOP_RULE_ID"]),
    ]
    missing = [(name, cols) for name, cols in fks if tuple(cols) not in existing]
    if not missing:
        return
    # SQLite 不支持 ALTER TABLE ADD CONSTRAINT，batch 会重建表；其余库直接加
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("SITE_BRUSH_TASK") as batch:
            for name, cols in missing:
                batch.create_foreign_key(name, "SITE_BRUSH_RULE", cols, ["ID"])
        return
    for name, cols in missing:
        op.create_foreign_key(name, "SITE_BRUSH_TASK", "SITE_BRUSH_RULE", cols, ["ID"])


def downgrade() -> None:
    if not has_table("SITE_BRUSH_TASK"):
        return
    existing = {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys("SITE_BRUSH_TASK")}
    names = [
        n
        for n in (
            "fk_site_brush_task_stop_rule_id",
            "fk_site_brush_task_remove_rule_id",
            "fk_site_brush_task_rss_rule_id",
        )
        if n in existing
    ]
    if names:
        if op.get_bind().dialect.name == "sqlite":
            with op.batch_alter_table("SITE_BRUSH_TASK") as batch:
                for n in names:
                    batch.drop_constraint(n, type_="foreignkey")
        else:
            for n in names:
                op.drop_constraint(n, "SITE_BRUSH_TASK", type_="foreignkey")
    if has_column("SITE_BRUSH_TASK", "STOP_RULE_ID"):
        op.drop_column("SITE_BRUSH_TASK", "STOP_RULE_ID")
    if has_column("SITE_BRUSH_TASK", "REMOVE_RULE_ID"):
        op.drop_column("SITE_BRUSH_TASK", "REMOVE_RULE_ID")
    if has_column("SITE_BRUSH_TASK", "RSS_RULE_ID"):
        op.drop_column("SITE_BRUSH_TASK", "RSS_RULE_ID")
