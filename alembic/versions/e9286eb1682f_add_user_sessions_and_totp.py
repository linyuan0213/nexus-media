"""add user sessions and totp

Revision ID: e9286eb1682f
Revises: d6812d1a731e
Create Date: 2026-11-10 21:05:11.316977

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "e9286eb1682f"
down_revision = "d6812d1a731e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("RBAC_USERS", sa.Column("TOTP_SECRET", sa.String(length=64), nullable=True))
    op.add_column(
        "RBAC_USERS",
        sa.Column("TOTP_ENABLED", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("RBAC_USERS", sa.Column("TOTP_RECOVERY_CODES", sa.Text(), nullable=True))

    op.add_column("RBAC_USER_LOGIN_LOGS", sa.Column("DEVICE_TYPE", sa.String(length=32), nullable=True))
    op.add_column("RBAC_USER_LOGIN_LOGS", sa.Column("DEVICE_MODEL", sa.String(length=128), nullable=True))
    op.add_column("RBAC_USER_LOGIN_LOGS", sa.Column("OS_NAME", sa.String(length=64), nullable=True))
    op.add_column("RBAC_USER_LOGIN_LOGS", sa.Column("BROWSER", sa.String(length=64), nullable=True))

    op.create_table(
        "RBAC_USER_SESSIONS",
        sa.Column("SESSION_ID", sa.String(length=64), nullable=False),
        sa.Column("USER_ID", sa.Integer(), nullable=False),
        sa.Column("REFRESH_JTI", sa.String(length=64), nullable=False),
        sa.Column("DEVICE_TYPE", sa.String(length=32), nullable=True),
        sa.Column("DEVICE_MODEL", sa.String(length=128), nullable=True),
        sa.Column("OS_NAME", sa.String(length=64), nullable=True),
        sa.Column("BROWSER", sa.String(length=64), nullable=True),
        sa.Column("LOGIN_IP", sa.String(length=64), nullable=True),
        sa.Column("USER_AGENT", sa.Text(), nullable=True),
        sa.Column("CREATED_AT", sa.DateTime(), nullable=False),
        sa.Column("LAST_SEEN_AT", sa.DateTime(), nullable=False),
        sa.Column("EXPIRES_AT", sa.DateTime(), nullable=False),
        sa.Column("REVOKED_AT", sa.DateTime(), nullable=True),
        sa.Column("REVOKE_REASON", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["USER_ID"], ["RBAC_USERS.ID"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("SESSION_ID"),
    )
    op.create_index("ix_RBAC_USER_SESSIONS_USER_ID", "RBAC_USER_SESSIONS", ["USER_ID"], unique=False)
    op.create_index(
        "ix_RBAC_USER_SESSIONS_REFRESH_JTI",
        "RBAC_USER_SESSIONS",
        ["REFRESH_JTI"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_RBAC_USER_SESSIONS_REFRESH_JTI", table_name="RBAC_USER_SESSIONS")
    op.drop_index("ix_RBAC_USER_SESSIONS_USER_ID", table_name="RBAC_USER_SESSIONS")
    op.drop_table("RBAC_USER_SESSIONS")
    op.drop_column("RBAC_USER_LOGIN_LOGS", "BROWSER")
    op.drop_column("RBAC_USER_LOGIN_LOGS", "OS_NAME")
    op.drop_column("RBAC_USER_LOGIN_LOGS", "DEVICE_MODEL")
    op.drop_column("RBAC_USER_LOGIN_LOGS", "DEVICE_TYPE")
    op.drop_column("RBAC_USERS", "TOTP_RECOVERY_CODES")
    op.drop_column("RBAC_USERS", "TOTP_ENABLED")
    op.drop_column("RBAC_USERS", "TOTP_SECRET")
