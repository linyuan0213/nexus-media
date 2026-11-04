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
    with op.batch_alter_table("TRANSFER_HISTORY") as batch_op:
        batch_op.create_unique_constraint(
            "uq_transfer_history_source_dest_backend",
            ["SOURCE_PATH", "SOURCE_FILENAME", "DEST_PATH", "DEST_FILENAME", "DST_BACKEND"],
        )


def downgrade() -> None:
    with op.batch_alter_table("TRANSFER_HISTORY") as batch_op:
        batch_op.drop_constraint("uq_transfer_history_source_dest_backend", type_="unique")
