"""add_unique_constraint_to_search_result_info

Revision ID: 7e029912f153
Revises: e5f6a7b8c9d0
Create Date: 2026-05-30 09:30:41.065328

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "7e029912f153"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # 1. Change PAGEURL from TEXT to VARCHAR(512) (MySQL requires this for unique constraints)
    with op.batch_alter_table("SEARCH_RESULT_INFO", schema=None) as batch_op:
        batch_op.alter_column("PAGEURL", type_=sa.String(512), existing_type=sa.Text)

    # 2. Deduplicate: keep the row with lowest ID for each (PAGEURL, SITE) pair
    # SQLite compatible syntax (MySQL uses DELETE t1 FROM... which SQLite doesn't support)
    conn.execute(
        sa.text("""
        DELETE FROM SEARCH_RESULT_INFO
        WHERE rowid IN (
            SELECT t1.rowid FROM SEARCH_RESULT_INFO t1
            INNER JOIN SEARCH_RESULT_INFO t2
            ON t1.PAGEURL = t2.PAGEURL AND t1.SITE = t2.SITE
            WHERE t1.ID > t2.ID
        )
    """)
    )

    # 3. Add unique index (SQLite does not support ALTER/ADD CONSTRAINT via batch)
    conn.execute(
        sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_search_pageurl_site
        ON SEARCH_RESULT_INFO (PAGEURL, SITE)
    """)
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS uq_search_pageurl_site"))
    with op.batch_alter_table("SEARCH_RESULT_INFO", schema=None) as batch_op:
        batch_op.alter_column("PAGEURL", type_=sa.Text, existing_type=sa.String(512))
