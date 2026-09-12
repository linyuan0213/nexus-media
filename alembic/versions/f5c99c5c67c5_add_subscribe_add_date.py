"""add ADD_DATE to SUBSCRIBE_MOVIES and SUBSCRIBE_TVS

Revision ID: f5c99c5c67c5
Revises: cd49db2e67f9
Create Date: 2026-09-08

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "f5c99c5c67c5"
down_revision = "cd49db2e67f9"
branch_labels = None
depends_on = None

_TABLE_COLUMNS = (
    ("SUBSCRIBE_MOVIES", "ADD_DATE"),
    ("SUBSCRIBE_TVS", "ADD_DATE"),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_column(table_name: str, column_name: str) -> bool:
    # 幂等：create_all 或既有库可能已含该列，重复 ADD COLUMN 会在各库报 duplicate column
    inspector = _inspector()
    if not inspector.has_table(table_name):
        return True
    return column_name.lower() in {c["name"].lower() for c in inspector.get_columns(table_name)}


def upgrade() -> None:
    for table_name, column_name in _TABLE_COLUMNS:
        if not _has_column(table_name, column_name):
            op.add_column(table_name, sa.Column(column_name, sa.String(255), nullable=True))


def downgrade() -> None:
    for table_name, column_name in reversed(_TABLE_COLUMNS):
        if not _has_column(table_name, column_name):
            continue
        op.drop_column(table_name, column_name)
