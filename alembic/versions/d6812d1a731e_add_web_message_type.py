"""add web message type

Revision ID: d6812d1a731e
Revises: d6fd2041dd02
Create Date: 2026-11-10 10:50:12.657633

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d6812d1a731e"
down_revision = "d6fd2041dd02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "AGENT_WEB_MESSAGE",
        sa.Column("MSG_TYPE", sa.String(length=64), nullable=False, server_default=""),
    )
    op.create_index(
        "idx_agent_web_msg_type",
        "AGENT_WEB_MESSAGE",
        ["MSG_TYPE", "ID"],
        unique=False,
    )
    # 历史统计消息回填稳定类型，避免升级后首次统计重复发送。
    op.execute(
        "UPDATE AGENT_WEB_MESSAGE SET MSG_TYPE='ptrefresh_date_message' "
        "WHERE MSG_TYPE='' AND TITLE LIKE '%站点数据统计%'"
    )


def downgrade() -> None:
    op.drop_index("idx_agent_web_msg_type", table_name="AGENT_WEB_MESSAGE")
    op.drop_column("AGENT_WEB_MESSAGE", "MSG_TYPE")
