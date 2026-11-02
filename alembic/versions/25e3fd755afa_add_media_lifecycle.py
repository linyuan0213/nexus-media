"""add media lifecycle

Revision ID: 25e3fd755afa
Revises: 1b0e0cf3dccc
Create Date: 2026-11-02 19:43:55.276811

"""

import sqlalchemy as sa

from alembic import op

revision = "25e3fd755afa"
down_revision = "1b0e0cf3dccc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "MEDIA_LIFECYCLE",
        sa.Column("ID", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("IDENTITY_ID", sa.String(length=26), nullable=False),
        sa.Column("MEDIA_TYPE", sa.String(length=16), nullable=False),
        sa.Column("SEASON", sa.Integer(), nullable=False),
        sa.Column("EPISODE", sa.Integer(), nullable=False),
        sa.Column("TITLE", sa.String(length=255), nullable=True),
        sa.Column("YEAR", sa.String(length=8), nullable=True),
        sa.Column("POSTER", sa.String(length=1024), nullable=True),
        sa.Column("STAGE", sa.String(length=32), nullable=False),
        sa.Column("STATUS", sa.String(length=16), nullable=False),
        sa.Column("RUN_ID", sa.String(length=64), nullable=True),
        sa.Column("TRACE_ID", sa.String(length=64), nullable=True),
        sa.Column("PROGRESS", sa.Integer(), nullable=False),
        sa.Column("SOURCE_PROVIDER", sa.String(length=64), nullable=True),
        sa.Column("CONTENT_PROFILE", sa.String(length=64), nullable=True),
        sa.Column("USER_ID", sa.Integer(), nullable=True),
        sa.Column("STAGE_STARTED_AT", sa.DateTime(), nullable=False),
        sa.Column("LAST_EVENT_AT", sa.DateTime(), nullable=False),
        sa.Column("NEXT_RETRY_AT", sa.DateTime(), nullable=True),
        sa.Column("RETRY_COUNT", sa.Integer(), nullable=False),
        sa.Column("LAST_ERROR", sa.Text(), nullable=True),
        sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
        sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("ID"),
        sa.UniqueConstraint("IDENTITY_ID", "SEASON", "EPISODE", name="UQ_MEDIA_LIFECYCLE_ITEM"),
    )
    op.create_index("INDX_MEDIA_LIFECYCLE_OWNER", "MEDIA_LIFECYCLE", ["USER_ID", "STATUS", "LAST_EVENT_AT"])
    op.create_index("INDX_MEDIA_LIFECYCLE_STAGE", "MEDIA_LIFECYCLE", ["STAGE", "STATUS", "LAST_EVENT_AT"])
    op.create_index("INDX_MEDIA_LIFECYCLE_TRACE", "MEDIA_LIFECYCLE", ["TRACE_ID"])
    op.create_index("ix_MEDIA_LIFECYCLE_USER_ID", "MEDIA_LIFECYCLE", ["USER_ID"])

    op.create_table(
        "MEDIA_LIFECYCLE_EVENT",
        sa.Column("ID", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("EVENT_KEY", sa.String(length=128), nullable=False),
        sa.Column("IDENTITY_ID", sa.String(length=26), nullable=False),
        sa.Column("MEDIA_TYPE", sa.String(length=16), nullable=False),
        sa.Column("SEASON", sa.Integer(), nullable=False),
        sa.Column("EPISODE", sa.Integer(), nullable=False),
        sa.Column("RUN_ID", sa.String(length=64), nullable=True),
        sa.Column("TRACE_ID", sa.String(length=64), nullable=True),
        sa.Column("STAGE", sa.String(length=32), nullable=False),
        sa.Column("EVENT_TYPE", sa.String(length=64), nullable=False),
        sa.Column("STATUS", sa.String(length=16), nullable=False),
        sa.Column("MESSAGE", sa.String(length=512), nullable=True),
        sa.Column("PAYLOAD", sa.Text(), nullable=True),
        sa.Column("USER_ID", sa.Integer(), nullable=True),
        sa.Column("OCCURRED_AT", sa.DateTime(), nullable=False),
        sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("ID"),
        sa.UniqueConstraint("EVENT_KEY", name="UQ_MEDIA_LIFECYCLE_EVENT_KEY"),
    )
    op.create_index(
        "INDX_MEDIA_LIFECYCLE_EVENT_ITEM",
        "MEDIA_LIFECYCLE_EVENT",
        ["IDENTITY_ID", "SEASON", "EPISODE", "OCCURRED_AT"],
    )
    op.create_index(
        "INDX_MEDIA_LIFECYCLE_EVENT_TRACE",
        "MEDIA_LIFECYCLE_EVENT",
        ["TRACE_ID", "OCCURRED_AT"],
    )
    op.create_index("ix_MEDIA_LIFECYCLE_EVENT_USER_ID", "MEDIA_LIFECYCLE_EVENT", ["USER_ID"])


def downgrade() -> None:
    op.drop_index("ix_MEDIA_LIFECYCLE_EVENT_USER_ID", table_name="MEDIA_LIFECYCLE_EVENT")
    op.drop_index("INDX_MEDIA_LIFECYCLE_EVENT_TRACE", table_name="MEDIA_LIFECYCLE_EVENT")
    op.drop_index("INDX_MEDIA_LIFECYCLE_EVENT_ITEM", table_name="MEDIA_LIFECYCLE_EVENT")
    op.drop_table("MEDIA_LIFECYCLE_EVENT")
    op.drop_index("ix_MEDIA_LIFECYCLE_USER_ID", table_name="MEDIA_LIFECYCLE")
    op.drop_index("INDX_MEDIA_LIFECYCLE_TRACE", table_name="MEDIA_LIFECYCLE")
    op.drop_index("INDX_MEDIA_LIFECYCLE_STAGE", table_name="MEDIA_LIFECYCLE")
    op.drop_index("INDX_MEDIA_LIFECYCLE_OWNER", table_name="MEDIA_LIFECYCLE")
    op.drop_table("MEDIA_LIFECYCLE")
