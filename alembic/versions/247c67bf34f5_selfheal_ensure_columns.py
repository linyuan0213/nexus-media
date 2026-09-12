"""self-heal: ensure required columns/tables exist (independent of prior stamp state)

面向"alembic 版本已在 head，但部分建表/加列未真正执行（被 stamp 或中途失败）"的库。
本迁移位于最末，故只要库版本 < 本 revision，`upgrade head` 就会执行并幂等补齐：
USER_ID 列与索引、RBAC 授权/绑定三表、订阅唯一索引、ADD_DATE、DST_BACKEND、SEEDS_*。
每步独立容错。

Revision ID: 247c67bf34f5
Revises: 35165c5e40c2
"""

import contextlib

import sqlalchemy as sa

from alembic import op

revision = "247c67bf34f5"
down_revision = "35165c5e40c2"
branch_labels = None
depends_on = None

INT_USER_ID_TABLES = [
    "SUBSCRIBE_MOVIES",
    "SUBSCRIBE_TVS",
    "SUBSCRIBE_HISTORY",
    "SUBSCRIBE_TV_EPISODES",
    "CONFIG_USER_RSS",
    "USERRSS_TASK_HISTORY",
    "DOWNLOAD_HISTORY",
]


def _insp():
    return sa.inspect(op.get_bind())


def _has_table(table: str) -> bool:
    return table in _insp().get_table_names()


def _has_column(table: str, column: str) -> bool:
    return _has_table(table) and column in [c["name"] for c in _insp().get_columns(table)]


def _has_index(table: str, index_name: str) -> bool:
    return _has_table(table) and index_name in [i.get("name") for i in _insp().get_indexes(table)]


def _add_column(table: str, name: str, column_type) -> None:
    if not _has_table(table) or _has_column(table, name):
        return
    with contextlib.suppress(Exception):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(name, column_type, nullable=True))


def _create_index(table: str, index_name: str, columns: list, unique: bool = False) -> None:
    if not _has_table(table) or _has_index(table, index_name):
        return
    if not all(_has_column(table, c) for c in columns):
        return
    with contextlib.suppress(Exception):
        op.create_index(index_name, table, columns, unique=unique)


def _create_grant_tables() -> None:
    if not _has_table("RBAC_ROLE_SITES"):
        fk_role = [sa.ForeignKey("RBAC_ROLES.ID", ondelete="CASCADE")] if _has_table("RBAC_ROLES") else []
        op.create_table(
            "RBAC_ROLE_SITES",
            sa.Column("ID", sa.Integer(), primary_key=True),
            sa.Column("ROLE_ID", sa.Integer(), *fk_role, nullable=False),
            sa.Column("SITE_NAME", sa.String(128), nullable=False),
            sa.Column("PERMISSIONS", sa.Text(), nullable=False),
            sa.Column("GRANTED_BY", sa.Integer(), nullable=True),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
            sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
        )
        _create_index("RBAC_ROLE_SITES", "ix_RBAC_ROLE_SITES_ROLE_ID", ["ROLE_ID"])
        _create_index("RBAC_ROLE_SITES", "UQ_RBAC_ROLE_SITES", ["ROLE_ID", "SITE_NAME"], unique=True)
    if not _has_table("RBAC_USER_SITES"):
        fk_user = [sa.ForeignKey("RBAC_USERS.ID", ondelete="CASCADE")] if _has_table("RBAC_USERS") else []
        op.create_table(
            "RBAC_USER_SITES",
            sa.Column("ID", sa.Integer(), primary_key=True),
            sa.Column("USER_ID", sa.Integer(), *fk_user, nullable=False),
            sa.Column("SITE_NAME", sa.String(128), nullable=False),
            sa.Column("PERMISSIONS", sa.Text(), nullable=False),
            sa.Column("GRANTED_BY", sa.Integer(), nullable=True),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
            sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
        )
        _create_index("RBAC_USER_SITES", "ix_RBAC_USER_SITES_USER_ID", ["USER_ID"])
        _create_index("RBAC_USER_SITES", "UQ_RBAC_USER_SITES", ["USER_ID", "SITE_NAME"], unique=True)
    if not _has_table("RBAC_USER_CHANNELS"):
        fk_user = [sa.ForeignKey("RBAC_USERS.ID", ondelete="CASCADE")] if _has_table("RBAC_USERS") else []
        op.create_table(
            "RBAC_USER_CHANNELS",
            sa.Column("ID", sa.Integer(), primary_key=True),
            sa.Column("USER_ID", sa.Integer(), *fk_user, nullable=False),
            sa.Column("CHANNEL", sa.String(64), nullable=False),
            sa.Column("CHANNEL_USER_ID", sa.String(255), nullable=False),
            sa.Column("STATUS", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
        )
        _create_index("RBAC_USER_CHANNELS", "ix_RBAC_USER_CHANNELS_USER_ID", ["USER_ID"])
        _create_index("RBAC_USER_CHANNELS", "UQ_RBAC_USER_CHANNELS", ["CHANNEL", "CHANNEL_USER_ID"], unique=True)


def upgrade() -> None:
    _create_grant_tables()
    for table in INT_USER_ID_TABLES:
        _add_column(table, "USER_ID", sa.Integer())
        _create_index(table, f"ix_{table}_USER_ID", ["USER_ID"])
    _add_column("SEARCH_RESULT_INFO", "USER_ID", sa.String(64))
    _create_index("SEARCH_RESULT_INFO", "ix_search_result_user_id", ["USER_ID"])
    _create_index("SUBSCRIBE_MOVIES", "UQ_SUBSCRIBE_MOVIES_USER_TMDB", ["USER_ID", "TMDBID"], unique=True)
    _create_index("SUBSCRIBE_TVS", "UQ_SUBSCRIBE_TVS_USER_TMDB_SEASON", ["USER_ID", "TMDBID", "SEASON"], unique=True)
    for table in ("SUBSCRIBE_MOVIES", "SUBSCRIBE_TVS"):
        _add_column(table, "ADD_DATE", sa.String(255))
    _add_column("TRANSFER_HISTORY", "DST_BACKEND", sa.String(64))
    for col in ("SEEDS_SEASON", "SEEDS_EPISODE", "SEEDS_END_EPISODE"):
        _add_column("SEARCH_RESULT_INFO", col, sa.Integer())


def downgrade() -> None:
    pass
