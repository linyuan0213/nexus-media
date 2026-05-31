"""add_search_session_id_to_search_result_info

Revision ID: cdf1444102e6
Revises: 7e029912f153
Create Date: 2026-05-31 11:43:45.360587

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Column

revision = "cdf1444102e6"
down_revision = "7e029912f153"
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not has_column("SEARCH_RESULT_INFO", "SEARCH_SESSION_ID"):
        op.add_column("SEARCH_RESULT_INFO", Column("SEARCH_SESSION_ID", sa.String(64), nullable=True))
        op.create_index(
            "ix_SEARCH_RESULT_INFO_SEARCH_SESSION_ID",
            "SEARCH_RESULT_INFO",
            ["SEARCH_SESSION_ID"],
            unique=False,
        )
    # 将唯一约束从 (PAGEURL, SITE) 改为 (PAGEURL, SITE, SEARCH_SESSION_ID)
    # 以支持多 session 隔离
    op.drop_constraint("uq_search_pageurl_site", "SEARCH_RESULT_INFO", type_="unique")
    op.create_unique_constraint(
        "uq_search_pageurl_site_session",
        "SEARCH_RESULT_INFO",
        ["PAGEURL", "SITE", "SEARCH_SESSION_ID"],
    )


def downgrade():
    op.drop_constraint("uq_search_pageurl_site_session", "SEARCH_RESULT_INFO", type_="unique")
    op.create_unique_constraint(
        "uq_search_pageurl_site",
        "SEARCH_RESULT_INFO",
        ["PAGEURL", "SITE"],
    )
    if has_column("SEARCH_RESULT_INFO", "SEARCH_SESSION_ID"):
        op.drop_index("ix_SEARCH_RESULT_INFO_SEARCH_SESSION_ID", table_name="SEARCH_RESULT_INFO")
        op.drop_column("SEARCH_RESULT_INFO", "SEARCH_SESSION_ID")
