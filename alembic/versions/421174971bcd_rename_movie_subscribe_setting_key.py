"""rename movie subscribe setting key

Revision ID: 421174971bcd
Revises: 25e3fd755afa
Create Date: 2026-11-03 22:28:03.255069

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "421174971bcd"
down_revision = "25e3fd755afa"
branch_labels = None
depends_on = None

LEGACY_PREFIX = "DefaultSubscribeSettingMOV"
CURRENT_PREFIX = "DefaultSubscribeSettingMovie"


def _rename_prefix(source: str, target: str) -> None:
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("SYSTEM_DICT"):
        return
    table = sa.Table("SYSTEM_DICT", sa.MetaData(), autoload_with=conn)
    keys = [row[0] for row in conn.execute(sa.select(table.c.KEY).where(table.c.TYPE == "SystemConfig")).fetchall()]
    existing = set(keys)
    # SQLite 的 LIKE 对 ASCII 大小写不敏感，必须在 Python 中做区分大小写的前缀匹配
    for key in keys:
        if not key.startswith(source):
            continue
        new_key = target + key[len(source) :]
        condition = sa.and_(table.c.TYPE == "SystemConfig", table.c.KEY == key)
        if new_key in existing:
            conn.execute(sa.delete(table).where(condition))
        else:
            conn.execute(sa.update(table).where(condition).values(KEY=new_key))


def upgrade() -> None:
    _rename_prefix(LEGACY_PREFIX, CURRENT_PREFIX)


def downgrade() -> None:
    _rename_prefix(CURRENT_PREFIX, LEGACY_PREFIX)
