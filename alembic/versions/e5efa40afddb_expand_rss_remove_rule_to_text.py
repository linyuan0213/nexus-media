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


def upgrade():
    op.alter_column("SITE_BRUSH_TASK", "RSS_RULE", existing_type=sa.String(255), type_=sa.Text, existing_nullable=True)
    op.alter_column(
        "SITE_BRUSH_TASK", "REMOVE_RULE", existing_type=sa.String(255), type_=sa.Text, existing_nullable=True
    )


def downgrade():
    op.alter_column("SITE_BRUSH_TASK", "RSS_RULE", existing_type=sa.Text, type_=sa.String(255), existing_nullable=True)
    op.alter_column(
        "SITE_BRUSH_TASK", "REMOVE_RULE", existing_type=sa.Text, type_=sa.String(255), existing_nullable=True
    )
