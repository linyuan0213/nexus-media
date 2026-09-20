"""widen subscribe list columns (EPISODES/RSS_SITES/SEARCH_SITES) to TEXT

MySQL 下 varchar(255) 存不下长集号列表（如 1..206）与较多站点列表，
新增订阅时会报 (1406) Data too long for column 'EPISODES'。

Revision ID: e1f2a3b4c5d6
Revises: 3dcf1ef5f1af
Create Date: 2026-09-20T00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "3dcf1ef5f1af"
branch_labels = None
depends_on = None

_TARGETS = (
    ("SUBSCRIBE_TV_EPISODES", ("EPISODES",)),
    ("SUBSCRIBE_TVS", ("RSS_SITES", "SEARCH_SITES")),
    ("SUBSCRIBE_MOVIES", ("RSS_SITES", "SEARCH_SITES")),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return False
    return column_name.lower() in {c["name"].lower() for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    dialect = op.get_bind().dialect.name
    for table_name, columns in _TARGETS:
        for column_name in columns:
            if not _has_column(table_name, column_name):
                continue
            if dialect == "sqlite":
                with op.batch_alter_table(table_name) as batch:
                    batch.alter_column(
                        column_name,
                        existing_type=sa.String(255),
                        type_=sa.Text(),
                        existing_nullable=None,
                    )
            else:
                op.alter_column(table_name, column_name, existing_type=sa.String(255), type_=sa.Text())


def downgrade() -> None:
    """收缩回 varchar(255)；因数据可能超长，先截断到 255 以保证降级必定可执行.

    注意：此操作会丢失超长部分（不可逆），仅用于回滚场景。
    """
    bind = op.get_bind()
    dialect = bind.dialect.name
    preparer = bind.dialect.identifier_preparer
    for table_name, columns in _TARGETS:
        for column_name in columns:
            if not _has_column(table_name, column_name):
                continue
            table = preparer.quote(table_name)
            column = preparer.quote(column_name)
            bind.execute(
                sa.text(f"UPDATE {table} SET {column} = SUBSTR({column}, 1, 255) WHERE LENGTH({column}) > 255")
            )
            if dialect == "sqlite":
                with op.batch_alter_table(table_name) as batch:
                    batch.alter_column(
                        column_name,
                        existing_type=sa.Text(),
                        type_=sa.String(255),
                        existing_nullable=None,
                    )
            else:
                op.alter_column(table_name, column_name, existing_type=sa.Text(), type_=sa.String(255))
