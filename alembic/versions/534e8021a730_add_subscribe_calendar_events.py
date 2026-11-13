"""add subscribe calendar events

Revision ID: 534e8021a730
Revises: c8227cd63ab2
Create Date: 2026-11-13 11:58:53.708231

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "534e8021a730"
down_revision = "c8227cd63ab2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "SUBSCRIBE_CALENDAR_EVENTS",
        sa.Column("ID", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("USER_ID", sa.Integer(), nullable=True),
        sa.Column("EVENT_KEY", sa.String(length=255), nullable=False),
        sa.Column("START", sa.String(length=10), nullable=False),
        sa.Column("DATA", sa.Text(), nullable=False),
        sa.Column("UPDATED_AT", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["USER_ID"], ["RBAC_USERS.ID"], ondelete="CASCADE"),
    )
    op.create_index(
        "UQ_SUBSCRIBE_CALENDAR_EVENT",
        "SUBSCRIBE_CALENDAR_EVENTS",
        ["USER_ID", "EVENT_KEY"],
        unique=True,
    )
    op.create_index(
        "INDX_SUBSCRIBE_CALENDAR_START",
        "SUBSCRIBE_CALENDAR_EVENTS",
        ["USER_ID", "START"],
        unique=False,
    )
    op.create_index(
        "ix_SUBSCRIBE_CALENDAR_EVENTS_USER_ID",
        "SUBSCRIBE_CALENDAR_EVENTS",
        ["USER_ID"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_SUBSCRIBE_CALENDAR_EVENTS_USER_ID", table_name="SUBSCRIBE_CALENDAR_EVENTS")
    op.drop_index("INDX_SUBSCRIBE_CALENDAR_START", table_name="SUBSCRIBE_CALENDAR_EVENTS")
    op.drop_index("UQ_SUBSCRIBE_CALENDAR_EVENT", table_name="SUBSCRIBE_CALENDAR_EVENTS")
    op.drop_table("SUBSCRIBE_CALENDAR_EVENTS")
