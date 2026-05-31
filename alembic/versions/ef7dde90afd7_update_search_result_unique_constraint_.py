"""update_search_result_unique_constraint_for_session

Revision ID: ef7dde90afd7
Revises: cdf1444102e6
Create Date: 2026-05-31 12:58:00.000000

"""

from alembic import op

revision = "ef7dde90afd7"
down_revision = "cdf1444102e6"
branch_labels = None
depends_on = None


def upgrade():
    # 创建唯一索引 (PAGEURL(191), SITE, SEARCH_SESSION_ID)
    # 使用前缀索引避免超过 MySQL InnoDB utf8mb4 的 3072 字节限制：
    # PAGEURL(191*4=764) + SITE(255*4=1020) + SEARCH_SESSION_ID(64*4=256) = 2040 bytes
    op.create_index(
        "uq_search_pageurl_site_session",
        "SEARCH_RESULT_INFO",
        ["PAGEURL", "SITE", "SEARCH_SESSION_ID"],
        unique=True,
        mysql_length={"PAGEURL": 191},
    )


def downgrade():
    op.drop_index("uq_search_pageurl_site_session", table_name="SEARCH_RESULT_INFO")
