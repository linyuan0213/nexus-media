"""fnos_config_api_key_to_username

Revision ID: 1ee439ce9b6d
Revises: 89c719931b5f
Create Date: 2026-06-21 07:30:58.659596

"""

import json

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision = "1ee439ce9b6d"
down_revision = "89c719931b5f"
branch_labels = None
depends_on = None


def _table_exists(table: str) -> bool:
    conn = op.get_bind()
    return table.upper() in {t.upper() for t in inspect(conn).get_table_names()}


def _update_fnos_config(conn, old_key: str, new_key: str) -> None:
    if not _table_exists("MEDIASERVER"):
        return
    rows = conn.execute(sa.text("SELECT ID, CONFIG FROM MEDIASERVER WHERE UPPER(NAME) = 'FNOS'")).fetchall()
    for row in rows:
        cfg = {}
        try:
            cfg = json.loads(row.CONFIG or "{}")
        except json.JSONDecodeError:
            continue
        if old_key in cfg and new_key not in cfg:
            cfg[new_key] = cfg.pop(old_key)
            conn.execute(
                sa.text("UPDATE MEDIASERVER SET CONFIG = :config WHERE ID = :id"),
                {"config": json.dumps(cfg, ensure_ascii=False), "id": row.ID},
            )


def upgrade() -> None:
    conn = op.get_bind()
    _update_fnos_config(conn, "api_key", "username")


def downgrade() -> None:
    conn = op.get_bind()
    _update_fnos_config(conn, "username", "api_key")
