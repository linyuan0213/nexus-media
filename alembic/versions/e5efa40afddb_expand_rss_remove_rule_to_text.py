"""expand_rss_remove_rule_to_text

Revision ID: e5efa40afddb
Revises: d4efa40afddb
Create Date: 2026-07-05 08:00:00

Change RSS_RULE and REMOVE_RULE from VARCHAR(255) to TEXT to support large JSON rules.
"""

import sqlalchemy as sa

from alembic import op

revision = "e5efa40afddb"
down_revision = "d4efa40afddb"
branch_labels = None
depends_on = None


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


def _alter_rule_columns(target_type, existing_type):
    cols = [c for c in ("RSS_RULE", "REMOVE_RULE") if has_column("SITE_BRUSH_TASK", c)]
    if not cols:
        return
    # SQLite 不支持 ALTER COLUMN，batch 会重建表；其余库直接改
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("SITE_BRUSH_TASK") as batch:
            for col in cols:
                batch.alter_column(col, existing_type=existing_type, type_=target_type, existing_nullable=True)
        return
    for col in cols:
        op.alter_column("SITE_BRUSH_TASK", col, existing_type=existing_type, type_=target_type, existing_nullable=True)


def upgrade():
    _alter_rule_columns(sa.Text(), sa.String(255))


def downgrade():
    _alter_rule_columns(sa.String(255), sa.Text())
