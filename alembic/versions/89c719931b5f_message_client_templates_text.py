"""message_client_templates_text

Revision ID: 89c719931b5f
Revises: e9d9eaed8d5c
Create Date: 2026-06-21 07:24:58.623450

"""

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "89c719931b5f"
down_revision = "e9d9eaed8d5c"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    conn = op.get_bind()
    cols = {c["name"].upper() for c in inspect(conn).get_columns(table)}
    return column.upper() in cols


def upgrade() -> None:
    if _column_exists("MESSAGE_CLIENT", "TEMPLATES"):
        with op.batch_alter_table("MESSAGE_CLIENT", schema=None) as batch_op:
            batch_op.alter_column(
                "TEMPLATES",
                existing_type=sa.String(length=255),
                type_=sa.Text,
                existing_nullable=False,
            )


def downgrade() -> None:
    if _column_exists("MESSAGE_CLIENT", "TEMPLATES"):
        with op.batch_alter_table("MESSAGE_CLIENT", schema=None) as batch_op:
            batch_op.alter_column(
                "TEMPLATES",
                existing_type=sa.Text,
                type_=sa.String(length=255),
                existing_nullable=False,
            )
