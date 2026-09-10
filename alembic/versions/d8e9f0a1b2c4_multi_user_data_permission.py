"""multi-user data permission: user_id columns and grant tables

ADR-021 多用户数据权限与站点访问控制：
1. 新建 RBAC_ROLE_SITES / RBAC_USER_SITES / RBAC_USER_CHANNELS
2. 订阅四表、自定义RSS及其历史、搜索结果、下载历史加 USER_ID 列
3. 存量订阅数据归属第一个 superadmin；SEARCH_RESULT_INFO 清空
4. 订阅唯一索引（先合并同用户重复订阅行）

Revision ID: d8e9f0a1b2c4
Revises: a8c14c1cc4c4
Create Date: 2026-09-09T00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d8e9f0a1b2c4"
down_revision = "a8c14c1cc4c4"
branch_labels = None
depends_on = None

# 加 USER_ID 列的表（ADR-021 5.1）
USER_ID_TABLES = [
    "SUBSCRIBE_MOVIES",
    "SUBSCRIBE_TVS",
    "SUBSCRIBE_HISTORY",
    "SUBSCRIBE_TV_EPISODES",
    "CONFIG_USER_RSS",
    "USERRSS_TASK_HISTORY",
    "DOWNLOAD_HISTORY",
]

# 业务行：随用户删除级联（ADR-021 5.7）
CASCADE_TABLES = {
    "SUBSCRIBE_MOVIES",
    "SUBSCRIBE_TVS",
    "SUBSCRIBE_HISTORY",
    "SUBSCRIBE_TV_EPISODES",
    "CONFIG_USER_RSS",
}

# 存量数据归属第一个 superadmin 的表
OWNED_TO_ADMIN_TABLES = [
    "SUBSCRIBE_MOVIES",
    "SUBSCRIBE_TVS",
    "SUBSCRIBE_HISTORY",
    "SUBSCRIBE_TV_EPISODES",
    "CONFIG_USER_RSS",
]


def has_table(table_name):
    conn = op.get_bind()
    return table_name in sa.inspect(conn).get_table_names()


def has_column(table_name, column_name):
    conn = op.get_bind()
    columns = [col["name"] for col in sa.inspect(conn).get_columns(table_name)]
    return column_name in columns


def _first_superadmin_user_id(conn):
    """查询第一个启用状态的 superadmin 用户 ID，无则 None."""
    if not has_table("RBAC_USERS"):
        return None
    users = sa.table("RBAC_USERS", sa.column("ID"), sa.column("STATUS"))
    user_roles = sa.table("RBAC_USER_ROLES", sa.column("user_id"), sa.column("role_id"))
    roles = sa.table("RBAC_ROLES", sa.column("ID"), sa.column("ROLE_CODE"))
    stmt = (
        sa.select(users.c.ID)
        .select_from(
            users.join(user_roles, user_roles.c.user_id == users.c.ID).join(roles, roles.c.ID == user_roles.c.role_id)
        )
        .where(roles.c.ROLE_CODE == "superadmin", users.c.STATUS == 1)
        .order_by(users.c.ID)
        .limit(1)
    )
    row = conn.execute(stmt).first()
    return row[0] if row else None


def _dedupe(conn, table_name: str, keys: list[str]) -> None:
    """按 keys 去重，保留最小 ID 行（建唯一索引前调用）.

    用 SQLAlchemy Core 表达式构造，保持跨库可移植：
    额外包一层 `keep` 派生表，满足 MySQL「DELETE 目标表不能直接在子查询中被引用」的限制。
    """
    table = sa.table(table_name, sa.column("ID"), *(sa.column(k) for k in keys))
    not_null = sa.and_(*(table.c[k].is_not(None) for k in keys))
    keep = (
        sa.select(sa.func.min(table.c.ID).label("ID")).where(not_null).group_by(*(table.c[k] for k in keys)).subquery()
    )
    conn.execute(
        sa.delete(table).where(
            table.c.ID.not_in(sa.select(keep.c.ID)),
            not_null,
        )
    )


def _has_index(table_name: str, index_name: str) -> bool:
    conn = op.get_bind()
    if table_name not in sa.inspect(conn).get_table_names():
        return False
    indexes = [idx["name"] for idx in sa.inspect(conn).get_indexes(table_name)]
    return index_name in indexes


def upgrade() -> None:
    # 1. 站点授权表（角色级 / 用户级）
    if not has_table("RBAC_ROLE_SITES"):
        op.create_table(
            "RBAC_ROLE_SITES",
            sa.Column("ID", sa.Integer(), primary_key=True),
            sa.Column(
                "ROLE_ID",
                sa.Integer(),
                sa.ForeignKey("RBAC_ROLES.ID", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("SITE_NAME", sa.String(128), nullable=False),
            sa.Column("PERMISSIONS", sa.Text(), nullable=False, server_default='["search"]'),
            sa.Column("GRANTED_BY", sa.Integer(), nullable=True),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
            sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_RBAC_ROLE_SITES_ROLE_ID", "RBAC_ROLE_SITES", ["ROLE_ID"])
        op.create_index("UQ_RBAC_ROLE_SITES", "RBAC_ROLE_SITES", ["ROLE_ID", "SITE_NAME"], unique=True)
    if not has_table("RBAC_USER_SITES"):
        op.create_table(
            "RBAC_USER_SITES",
            sa.Column("ID", sa.Integer(), primary_key=True),
            sa.Column(
                "USER_ID",
                sa.Integer(),
                sa.ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("SITE_NAME", sa.String(128), nullable=False),
            sa.Column("PERMISSIONS", sa.Text(), nullable=False, server_default='["search"]'),
            sa.Column("GRANTED_BY", sa.Integer(), nullable=True),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
            sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_RBAC_USER_SITES_USER_ID", "RBAC_USER_SITES", ["USER_ID"])
        op.create_index("UQ_RBAC_USER_SITES", "RBAC_USER_SITES", ["USER_ID", "SITE_NAME"], unique=True)

    # 2. 渠道绑定表
    if not has_table("RBAC_USER_CHANNELS"):
        op.create_table(
            "RBAC_USER_CHANNELS",
            sa.Column("ID", sa.Integer(), primary_key=True),
            sa.Column(
                "USER_ID",
                sa.Integer(),
                sa.ForeignKey("RBAC_USERS.ID", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("CHANNEL", sa.String(64), nullable=False),
            sa.Column("CHANNEL_USER_ID", sa.String(255), nullable=False),
            sa.Column("STATUS", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
        )
        op.create_index("ix_RBAC_USER_CHANNELS_USER_ID", "RBAC_USER_CHANNELS", ["USER_ID"])
        op.create_index("UQ_RBAC_USER_CHANNELS", "RBAC_USER_CHANNELS", ["CHANNEL", "CHANNEL_USER_ID"], unique=True)

    # 3. 业务表加 USER_ID 列（SQLite 走 batch_alter_table）
    for table in USER_ID_TABLES:
        if not has_table(table) or has_column(table, "USER_ID"):
            continue
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column("USER_ID", sa.Integer(), nullable=True))
            batch_op.create_index(f"ix_{table}_USER_ID", ["USER_ID"])
            batch_op.create_foreign_key(
                f"fk_{table}_USER_ID",
                "RBAC_USERS",
                ["USER_ID"],
                ["ID"],
                ondelete="CASCADE" if table in CASCADE_TABLES else "SET NULL",
            )

    # 4. 存量数据归属第一个 superadmin
    conn = op.get_bind()
    admin_id = _first_superadmin_user_id(conn)
    if admin_id is not None:
        for table in OWNED_TO_ADMIN_TABLES:
            if has_table(table) and has_column(table, "USER_ID"):
                conn.execute(sa.text(f"UPDATE {table} SET USER_ID = :uid WHERE USER_ID IS NULL"), {"uid": admin_id})

    # 搜索结果有 24h 概率清理，直接清空避免跨用户串数据
    if has_table("SEARCH_RESULT_INFO"):
        conn.execute(sa.text("DELETE FROM SEARCH_RESULT_INFO"))

    # 5. 订阅唯一索引（先去重；幂等：已存在则跳过）
    if has_table("SUBSCRIBE_MOVIES"):
        _dedupe(conn, "SUBSCRIBE_MOVIES", ["USER_ID", "TMDBID"])
        if not _has_index("SUBSCRIBE_MOVIES", "UQ_SUBSCRIBE_MOVIES_USER_TMDB"):
            op.create_index("UQ_SUBSCRIBE_MOVIES_USER_TMDB", "SUBSCRIBE_MOVIES", ["USER_ID", "TMDBID"], unique=True)
    if has_table("SUBSCRIBE_TVS"):
        _dedupe(conn, "SUBSCRIBE_TVS", ["USER_ID", "TMDBID", "SEASON"])
        if not _has_index("SUBSCRIBE_TVS", "UQ_SUBSCRIBE_TVS_USER_TMDB_SEASON"):
            op.create_index(
                "UQ_SUBSCRIBE_TVS_USER_TMDB_SEASON", "SUBSCRIBE_TVS", ["USER_ID", "TMDBID", "SEASON"], unique=True
            )


def downgrade() -> None:
    for index, table in [
        ("UQ_SUBSCRIBE_TVS_USER_TMDB_SEASON", "SUBSCRIBE_TVS"),
        ("UQ_SUBSCRIBE_MOVIES_USER_TMDB", "SUBSCRIBE_MOVIES"),
    ]:
        if has_table(table):
            op.drop_index(index, table_name=table)
    for table in USER_ID_TABLES:
        if has_table(table) and has_column(table, "USER_ID"):
            with op.batch_alter_table(table) as batch_op:
                batch_op.drop_constraint(f"fk_{table}_USER_ID", type_="foreignkey")
                batch_op.drop_index(f"ix_{table}_USER_ID")
                batch_op.drop_column("USER_ID")
    for table in ["RBAC_USER_CHANNELS", "RBAC_USER_SITES", "RBAC_ROLE_SITES"]:
        if has_table(table):
            op.drop_table(table)
