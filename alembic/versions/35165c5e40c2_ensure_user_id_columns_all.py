"""ensure USER_ID columns on ADR-021 business tables

自愈迁移：部分库 alembic 版本已到 head，但 d8e9f0a1b2c4 里的加列未实际执行
（被 stamp 或中断），导致 USER_ID 缺列报错。这里幂等补齐列与索引，重复执行安全。

Revision ID: 35165c5e40c2
Revises: d8e9f0a1b2c4
Create Date: 2026-09-12T00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "35165c5e40c2"
down_revision = "d8e9f0a1b2c4"
branch_labels = None
depends_on = None

# 需要 USER_ID 的业务表（与 d8e9f0a1b2c4 保持一致）
INT_USER_ID_TABLES = [
    "SUBSCRIBE_MOVIES",
    "SUBSCRIBE_TVS",
    "SUBSCRIBE_HISTORY",
    "SUBSCRIBE_TV_EPISODES",
    "CONFIG_USER_RSS",
    "USERRSS_TASK_HISTORY",
    "DOWNLOAD_HISTORY",
]


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _inspector().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in _inspector().get_columns(table)]


def _has_index(table: str, index_name: str) -> bool:
    return index_name in [i.get("name") for i in _inspector().get_indexes(table)]


def _add_user_id(table: str, column_type) -> None:
    if not _has_table(table):
        return
    if not _has_column(table, "USER_ID"):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("USER_ID", column_type, nullable=True))
    index_name = "ix_search_result_user_id" if table == "SEARCH_RESULT_INFO" else f"ix_{table}_USER_ID"
    if not _has_index(table, index_name):
        op.create_index(index_name, table, ["USER_ID"])


def upgrade() -> None:
    for table in INT_USER_ID_TABLES:
        _add_user_id(table, sa.Integer())
    _add_user_id("SEARCH_RESULT_INFO", sa.String(64))


def downgrade() -> None:
    # 自愈迁移不做破坏性回滚（列可能被其它迁移管理）
    pass
