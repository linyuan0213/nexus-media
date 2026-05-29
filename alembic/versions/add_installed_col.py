"""add_plugin_manifest_installed

Revision ID: add_installed_col
Revises: 8b7846a02c03
Create Date: 2026-05-05

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import Boolean, Column

revision = "add_installed_col"
down_revision = "8b7846a02c03"
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not has_column("PLUGIN_MANIFEST", "INSTALLED"):
        op.add_column("PLUGIN_MANIFEST", Column("INSTALLED", Boolean, nullable=False, server_default="1"))


def downgrade():
    if has_column("PLUGIN_MANIFEST", "INSTALLED"):
        op.drop_column("PLUGIN_MANIFEST", "INSTALLED")
