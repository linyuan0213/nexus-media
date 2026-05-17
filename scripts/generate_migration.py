#!/usr/bin/env python3
"""
生成 Alembic 数据库迁移脚本（空壳模板）

用法:
    uv run python scripts/generate_migration.py "添加 SITE_BRUSH_RULE 表"

由于项目历史模型与数据库 schema 存在差异，autogenerate 会产生大量垃圾迁移，
因此本脚本只生成空壳模板，开发者需手动在 upgrade()/downgrade() 中填写实际 DDL。

文件名格式: {revision_id}_{描述}_{版本号}.py
"""

import os
import random
import string
import sys

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from version import APP_VERSION  # noqa: E402


def _random_rev_id(length: int = 12) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))


def _slugify(text: str) -> str:
    return (
        text.strip()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(".", "_")
        .replace(",", "_")
        .replace(";", "_")
        .replace(":", "_")
        .replace("'", "")
        .replace('"', "")
        .replace("(", "")
        .replace(")", "")
        .replace("[", "")
        .replace("]", "")
        .replace("{", "")
        .replace("}", "")
        .replace("#", "")
        .replace("@", "")
        .replace("!", "")
        .replace("?", "")
        .replace("&", "")
        .replace("*", "")
        .replace("+", "")
        .replace("=", "")
        .replace("<", "")
        .replace(">", "")
        .replace("|", "")
        .replace("^", "")
        .replace("~", "")
        .replace("`", "")
        .replace("$", "")
        .replace("%", "")
    )


def _get_head_revision(versions_dir: str) -> str | None:
    """按迁移链找到真正的 head revision（不被任何其他迁移引用的那个）"""
    revs: dict[str, str | None] = {}
    for fname in os.listdir(versions_dir):
        if not fname.endswith(".py") or fname.startswith("__"):
            continue
        path = os.path.join(versions_dir, fname)
        rev: str | None = None
        down: str | None = None
        with open(path, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("revision = "):
                    rev = s.split("=", 1)[1].strip().strip('"').strip("'")
                elif s.startswith("down_revision = "):
                    val = s.split("=", 1)[1].strip().strip('"').strip("'")
                    down = val if val != "None" else None
        if rev is not None:
            revs[rev] = down

    if not revs:
        return None

    # 找到 base（down_revision = None）
    bases = [r for r, d in revs.items() if d is None]
    if not bases:
        return None

    # 沿着链走到 head
    current = bases[0]
    child_map = {d: r for r, d in revs.items() if d is not None}
    while current in child_map:
        current = child_map[current]

    return current


def generate_migration(message: str) -> None:
    rev_id = _random_rev_id()
    slug = _slugify(message)
    version = APP_VERSION.replace(".", "_")
    versions_dir = os.path.join(_root, "scripts", "versions")
    head_rev = _get_head_revision(versions_dir)

    filename = f"{rev_id}_{slug}_{version}.py"
    filepath = os.path.join(versions_dir, filename)

    down_rev_line = f'down_revision = "{head_rev}"' if head_rev else "down_revision = None"

    content = f'''"""{message}

Revision ID: {rev_id}
Revises: {head_rev or "None"}
Create Date: {__import__("datetime").datetime.now().isoformat()}

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "{rev_id}"
{down_rev_line}
branch_labels = None
depends_on = None


def has_column(table_name, column_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def has_table(table_name):
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
'''

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"迁移脚本已生成: scripts/versions/{filename}")
    print(f"  revision: {rev_id}")
    print(f"  down_revision: {head_rev or 'None'}")
    print("请手动编辑 upgrade()/downgrade() 填写实际 DDL 逻辑。")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: uv run python scripts/generate_migration.py '迁移描述'")
        sys.exit(1)

    msg = sys.argv[1]
    generate_migration(msg)
