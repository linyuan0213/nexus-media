"""expand site api credential data

Revision ID: c8227cd63ab2
Revises: 360076f14179
Create Date: 2026-11-12 09:37:06.872810

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "c8227cd63ab2"
down_revision = "360076f14179"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE CONFIG_SITE_API_CREDENTIAL MODIFY DATA MEDIUMTEXT NOT NULL")


def downgrade() -> None:
    if op.get_bind().dialect.name == "mysql":
        op.execute("ALTER TABLE CONFIG_SITE_API_CREDENTIAL MODIFY DATA TEXT NOT NULL")
