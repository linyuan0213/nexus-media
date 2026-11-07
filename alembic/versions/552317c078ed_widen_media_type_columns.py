"""widen media type columns

Revision ID: 552317c078ed
Revises: 9d0379c17274
Create Date: 2026-11-07 10:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "552317c078ed"
down_revision = "9d0379c17274"
branch_labels = None
depends_on = None

_TABLES = ("MEDIA_IDENTITY", "MEDIA_EXTERNAL_REF", "MEDIA_LIFECYCLE", "MEDIA_LIFECYCLE_EVENT")


def _alter(table: str, old: sa.String, new: sa.String) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table(table) as batch:
            batch.alter_column("MEDIA_TYPE", type_=new, existing_type=old)
        return
    op.alter_column(table, "MEDIA_TYPE", type_=new, existing_type=old)


def upgrade() -> None:
    for table in _TABLES:
        _alter(table, sa.String(16), sa.String(128))


def downgrade() -> None:
    for table in _TABLES:
        _alter(table, sa.String(128), sa.String(16))
