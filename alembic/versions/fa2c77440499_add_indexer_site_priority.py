"""add indexer site priority

Revision ID: fa2c77440499
Revises: 421174971bcd
Create Date: 2026-11-03 23:19:45.320095

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "fa2c77440499"
down_revision = "421174971bcd"
branch_labels = None
depends_on = None


def _has_priority() -> bool:
    inspector = sa.inspect(op.get_bind())
    if "INDEXER_SITE_CONFIG" not in inspector.get_table_names():
        return True
    return "PRIORITY" in {column["name"] for column in inspector.get_columns("INDEXER_SITE_CONFIG")}


def upgrade() -> None:
    if _has_priority():
        return
    op.add_column("INDEXER_SITE_CONFIG", sa.Column("PRIORITY", sa.Integer(), nullable=True))


def downgrade() -> None:
    if not _has_priority():
        return
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("INDEXER_SITE_CONFIG") as batch_op:
            batch_op.drop_column("PRIORITY")
    else:
        op.drop_column("INDEXER_SITE_CONFIG", "PRIORITY")
