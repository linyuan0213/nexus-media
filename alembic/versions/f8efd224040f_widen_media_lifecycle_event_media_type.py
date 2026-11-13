"""widen media lifecycle event media type

Revision ID: f8efd224040f
Revises: 534e8021a730
Create Date: 2026-11-13 18:45:03.946619

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f8efd224040f"
down_revision = "534e8021a730"
branch_labels = None
depends_on = None


def _alter_column(table: str, column: str, old, new) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, type_=new, existing_type=old)
        return
    op.alter_column(table, column, type_=new, existing_type=old)


def upgrade() -> None:
    _alter_column("MEDIA_LIFECYCLE_EVENT", "MEDIA_TYPE", sa.String(16), sa.String(128))
    for table in ("DOWNLOAD_HISTORY", "SUBSCRIBE_HISTORY", "SUBSCRIBE_MOVIES", "SUBSCRIBE_TVS"):
        _alter_column(table, "DESC", sa.String(255), sa.Text())


def downgrade() -> None:
    for table in ("DOWNLOAD_HISTORY", "SUBSCRIBE_HISTORY", "SUBSCRIBE_MOVIES", "SUBSCRIBE_TVS"):
        _alter_column(table, "DESC", sa.Text(), sa.String(255))
    _alter_column("MEDIA_LIFECYCLE_EVENT", "MEDIA_TYPE", sa.String(128), sa.String(16))
