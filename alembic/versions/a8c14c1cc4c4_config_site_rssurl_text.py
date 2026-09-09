"""CONFIG_SITE.RSSURL: varchar(512) -> TEXT

RSS 地址可携带长参数（M-Team 签名等），部分站点 RSS URL 超过 512 触发
MySQL 1406 Data too long，改为 TEXT 无长度限制。

Revision ID: a8c14c1cc4c4
Revises: f5c99c5c67c5
Create Date: 2026-09-09T00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

revision = "a8c14c1cc4c4"
down_revision = "f5c99c5c67c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "CONFIG_SITE",
        "RSSURL",
        existing_type=sa.String(length=512),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "CONFIG_SITE",
        "RSSURL",
        existing_type=sa.Text(),
        type_=sa.String(length=512),
        existing_nullable=True,
    )
