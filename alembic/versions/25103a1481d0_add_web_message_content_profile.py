"""add web message content profile

Revision ID: 25103a1481d0
Revises: fa2c77440499
Create Date: 2026-11-04 13:48:19.810851

"""
import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = '25103a1481d0'
down_revision = 'fa2c77440499'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "AGENT_WEB_MESSAGE",
        sa.Column("CONTENT_PROFILE", sa.String(length=32), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("AGENT_WEB_MESSAGE", "CONTENT_PROFILE")
