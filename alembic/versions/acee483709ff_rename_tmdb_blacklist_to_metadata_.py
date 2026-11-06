"""rename tmdb blacklist to metadata blacklist

Revision ID: acee483709ff
Revises: 2e5752776552
Create Date: 2026-11-06 17:33:48.402563

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "acee483709ff"
down_revision = "2e5752776552"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE RBAC_MENUS SET MENU_NAME = '识别黑名单' WHERE MENU_CODE = 'RenameBlacklist'")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("TMDB_BLACKLIST") as batch:
            batch.alter_column("TMDB_ID", new_column_name="EXTERNAL_ID")
            batch.add_column(sa.Column("PROVIDER", sa.String(50), nullable=False, server_default="tmdb"))
        op.rename_table("TMDB_BLACKLIST", "METADATA_BLACKLIST")
        return

    op.rename_table("TMDB_BLACKLIST", "METADATA_BLACKLIST")
    op.alter_column(
        "METADATA_BLACKLIST",
        "TMDB_ID",
        new_column_name="EXTERNAL_ID",
        existing_type=sa.String(50),
    )
    op.add_column(
        "METADATA_BLACKLIST",
        sa.Column("PROVIDER", sa.String(50), nullable=False, server_default="tmdb"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("METADATA_BLACKLIST") as batch:
            batch.drop_column("PROVIDER")
            batch.alter_column("EXTERNAL_ID", new_column_name="TMDB_ID")
        op.rename_table("METADATA_BLACKLIST", "TMDB_BLACKLIST")
        return

    op.drop_column("METADATA_BLACKLIST", "PROVIDER")
    op.alter_column(
        "METADATA_BLACKLIST",
        "EXTERNAL_ID",
        new_column_name="TMDB_ID",
        existing_type=sa.String(50),
    )
    op.rename_table("METADATA_BLACKLIST", "TMDB_BLACKLIST")
