"""add_indexes_for_query_performance

Revision ID: e9d9eaed8d5c
Revises: f65506008fd7
Create Date: 2026-06-14 00:04:17.631361

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e9d9eaed8d5c"
down_revision = "f65506008fd7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    with op.batch_alter_table("CONFIG_USER_RSS", schema=None) as batch_op:
        if dialect == "mysql":
            batch_op.alter_column("STATE", type_=sa.String(255), existing_nullable=True)
        batch_op.create_index(batch_op.f("ix_CONFIG_USER_RSS_STATE"), ["STATE"], unique=False)

    with op.batch_alter_table("SITE_BRUSH_TORRENTS", schema=None) as batch_op:
        batch_op.create_index("INDX_SITE_BRUSH_TORRENTS_ENCLOSURE", ["ENCLOSURE"], unique=False, mysql_length=255)
        batch_op.create_index("INDX_SITE_BRUSH_TORRENTS_TASK_ID", ["TASK_ID"], unique=False)

    with op.batch_alter_table("SUBSCRIBE_MOVIES", schema=None) as batch_op:
        if dialect == "mysql":
            batch_op.alter_column("STATE", type_=sa.String(255), existing_nullable=True)
            batch_op.alter_column("TMDBID", type_=sa.String(255), existing_nullable=True)
        batch_op.create_index(batch_op.f("ix_SUBSCRIBE_MOVIES_STATE"), ["STATE"], unique=False)
        batch_op.create_index(batch_op.f("ix_SUBSCRIBE_MOVIES_TMDBID"), ["TMDBID"], unique=False)

    with op.batch_alter_table("SUBSCRIBE_TVS", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_SUBSCRIBE_TVS_STATE"), ["STATE"], unique=False)
        batch_op.create_index(batch_op.f("ix_SUBSCRIBE_TVS_TMDBID"), ["TMDBID"], unique=False)

    with op.batch_alter_table("TRANSFER_HISTORY", schema=None) as batch_op:
        batch_op.create_index("INDX_TRANSFER_HISTORY_SOURCE", ["SOURCE_PATH", "SOURCE_FILENAME"], unique=False)
        batch_op.create_index(batch_op.f("ix_TRANSFER_HISTORY_TMDBID"), ["TMDBID"], unique=False)

    with op.batch_alter_table("TRANSFER_UNKNOWN", schema=None) as batch_op:
        batch_op.create_index("INDX_TRANSFER_UNKNOWN_PATH_STATE", ["PATH", "STATE"], unique=False)


def downgrade() -> None:
    dialect = op.get_bind().dialect.name

    with op.batch_alter_table("TRANSFER_UNKNOWN", schema=None) as batch_op:
        batch_op.drop_index("INDX_TRANSFER_UNKNOWN_PATH_STATE")

    with op.batch_alter_table("TRANSFER_HISTORY", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_TRANSFER_HISTORY_TMDBID"))
        batch_op.drop_index("INDX_TRANSFER_HISTORY_SOURCE")

    with op.batch_alter_table("SUBSCRIBE_TVS", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_SUBSCRIBE_TVS_TMDBID"))
        batch_op.drop_index(batch_op.f("ix_SUBSCRIBE_TVS_STATE"))

    with op.batch_alter_table("SUBSCRIBE_MOVIES", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_SUBSCRIBE_MOVIES_TMDBID"))
        batch_op.drop_index(batch_op.f("ix_SUBSCRIBE_MOVIES_STATE"))
        if dialect == "mysql":
            batch_op.alter_column("TMDBID", type_=sa.Text, existing_nullable=True)
            batch_op.alter_column("STATE", type_=sa.Text, existing_nullable=True)

    with op.batch_alter_table("SITE_BRUSH_TORRENTS", schema=None) as batch_op:
        batch_op.drop_index("INDX_SITE_BRUSH_TORRENTS_TASK_ID")
        batch_op.drop_index("INDX_SITE_BRUSH_TORRENTS_ENCLOSURE")

    with op.batch_alter_table("CONFIG_USER_RSS", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_CONFIG_USER_RSS_STATE"))
        if dialect == "mysql":
            batch_op.alter_column("STATE", type_=sa.Text, existing_nullable=True)
