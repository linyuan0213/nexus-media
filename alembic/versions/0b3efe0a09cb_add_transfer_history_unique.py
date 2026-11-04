"""add transfer history unique

Revision ID: 0b3efe0a09cb
Revises: 25103a1481d0
Create Date: 2026-11-04 22:51:13.355178

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "0b3efe0a09cb"
down_revision = "25103a1481d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "uq_transfer_history_source_dest_backend",
        "TRANSFER_HISTORY",
        ["SOURCE_PATH", "SOURCE_FILENAME", "DEST_PATH", "DEST_FILENAME", "DST_BACKEND"],
        unique=True,
        mysql_length={
            "SOURCE_PATH": 128,
            "SOURCE_FILENAME": 128,
            "DEST_PATH": 128,
            "DEST_FILENAME": 128,
            "DST_BACKEND": 64,
        },
    )


def downgrade() -> None:
    op.drop_index("uq_transfer_history_source_dest_backend", table_name="TRANSFER_HISTORY")
