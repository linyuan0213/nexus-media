"""widen metadata snapshot payload

Revision ID: 2e5752776552
Revises: 037e7bbf796b
Create Date: 2026-11-06 16:04:07.241659

"""

import sqlalchemy as sa
from sqlalchemy.dialects import mysql

from alembic import op

# revision identifiers, used by Alembic.
revision = "2e5752776552"
down_revision = "037e7bbf796b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLite 不支持 ALTER COLUMN；TEXT 与 LONGTEXT 变体在 SQLite 下等价，直接跳过。
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "MEDIA_METADATA_SNAPSHOT",
        "PAYLOAD",
        existing_type=sa.Text(),
        type_=sa.Text().with_variant(mysql.LONGTEXT(), "mysql"),
        existing_nullable=False,
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "MEDIA_METADATA_SNAPSHOT",
        "PAYLOAD",
        existing_type=sa.Text().with_variant(mysql.LONGTEXT(), "mysql"),
        type_=sa.Text(),
        existing_nullable=False,
    )
