"""ensure USER_ID column on SEARCH_RESULT_INFO

修复部分库（alembic 版本已到 head 但 t1u2v3w4x5y6 未实际执行）缺失
SEARCH_RESULT_INFO.USER_ID 的问题；幂等，可安全重复执行。

Revision ID: 8599a96d1abd
Revises: d8e9f0a1b2c4
Create Date: 2026-09-11T00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "8599a96d1abd"
down_revision = "d8e9f0a1b2c4"
branch_labels = None
depends_on = None


def has_table(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column_name in [c["name"] for c in inspector.get_columns(table_name)]


def has_index(table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return index_name in [i.get("name") for i in inspector.get_indexes(table_name)]


def upgrade() -> None:
    if not has_table("SEARCH_RESULT_INFO"):
        return
    if not has_column("SEARCH_RESULT_INFO", "USER_ID"):
        with op.batch_alter_table("SEARCH_RESULT_INFO") as batch_op:
            batch_op.add_column(sa.Column("USER_ID", sa.String(64), nullable=True))
    if not has_index("SEARCH_RESULT_INFO", "ix_search_result_user_id"):
        op.create_index("ix_search_result_user_id", "SEARCH_RESULT_INFO", ["USER_ID"])


def downgrade() -> None:
    if not has_table("SEARCH_RESULT_INFO"):
        return
    if has_index("SEARCH_RESULT_INFO", "ix_search_result_user_id"):
        op.drop_index("ix_search_result_user_id", table_name="SEARCH_RESULT_INFO")
    if has_column("SEARCH_RESULT_INFO", "USER_ID"):
        with op.batch_alter_table("SEARCH_RESULT_INFO") as batch_op:
            batch_op.drop_column("USER_ID")
