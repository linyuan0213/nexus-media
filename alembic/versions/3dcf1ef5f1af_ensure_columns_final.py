"""ensure required columns exist (final self-heal)

对"alembic 版本已在 head 但历史加列未执行"的库，必须有一个**更靠后的 revision**
才会被 `alembic upgrade head` 执行。本迁移只做幂等 ADD COLUMN（失败显式抛错），
不建表、不建索引，避免误伤数据。

Revision ID: 3dcf1ef5f1af
Revises: 247c67bf34f5
"""

import sqlalchemy as sa

from alembic import op

revision = "3dcf1ef5f1af"
down_revision = "247c67bf34f5"
branch_labels = None
depends_on = None

# 表 -> [(列名, 类型)]
REQUIRED_COLUMNS = {
    "SUBSCRIBE_MOVIES": [("USER_ID", sa.Integer()), ("ADD_DATE", sa.String(255))],
    "SUBSCRIBE_TVS": [("USER_ID", sa.Integer()), ("ADD_DATE", sa.String(255))],
    "SUBSCRIBE_HISTORY": [("USER_ID", sa.Integer())],
    "SUBSCRIBE_TV_EPISODES": [("USER_ID", sa.Integer())],
    "CONFIG_USER_RSS": [("USER_ID", sa.Integer())],
    "USERRSS_TASK_HISTORY": [("USER_ID", sa.Integer())],
    "DOWNLOAD_HISTORY": [("USER_ID", sa.Integer())],
    "TRANSFER_HISTORY": [("DST_BACKEND", sa.String(64))],
    "SEARCH_RESULT_INFO": [
        ("USER_ID", sa.String(64)),
        ("SEEDS_SEASON", sa.Integer()),
        ("SEEDS_EPISODE", sa.Integer()),
        ("SEEDS_END_EPISODE", sa.Integer()),
    ],
}


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in _insp().get_columns(table)]


def upgrade() -> None:
    for table, columns in REQUIRED_COLUMNS.items():
        if not _has_table(table):
            continue
        for name, column_type in columns:
            if _has_column(table, name):
                continue
            with op.batch_alter_table(table) as batch_op:
                batch_op.add_column(sa.Column(name, column_type, nullable=True))


def downgrade() -> None:
    pass
