"""refresh message client type labels

Revision ID: d6fd2041dd02
Revises: 705da066a007
Create Date: 2026-11-07 12:33:48.887742

"""

import json
import re

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d6fd2041dd02"
down_revision = "705da066a007"
branch_labels = None
depends_on = None


_TYPE_EXPR = re.compile(r"\{\{\s*media_info\.type\.value\s*\}\}")
_MOVIE_COND = re.compile(r"media_info\.type\.value\s*==\s*['\"]电影['\"]")
_NEW_TYPE = "{% if profile_label %}{{ profile_label }}{% else %}{{ type_label }}{% endif %}"


def _rewrite(raw: str, *, reverse: bool = False) -> str | None:
    try:
        outer = json.loads(raw)
    except (TypeError, ValueError):
        return None
    double_encoded = isinstance(outer, str)
    if double_encoded:
        try:
            data = json.loads(outer)
        except (TypeError, ValueError):
            return None
    else:
        data = outer
    if not isinstance(data, dict):
        return None
    changed = False
    for template in data.values():
        if not isinstance(template, dict):
            continue
        for field in ("title", "text"):
            value = template.get(field)
            if not isinstance(value, str):
                continue
            if reverse:
                updated = value.replace(_NEW_TYPE, "{{ media_info.type.value }}")
            else:
                updated = _TYPE_EXPR.sub(_NEW_TYPE, value)
                updated = _MOVIE_COND.sub("media_info.type.value == 'movie'", updated)
            if updated != value:
                template[field] = updated
                changed = True
    if not changed:
        return None
    inner = json.dumps(data, ensure_ascii=False)
    return json.dumps(inner, ensure_ascii=False) if double_encoded else inner


def _refresh(*, reverse: bool = False) -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT ID, TEMPLATES FROM MESSAGE_CLIENT")).fetchall()
    for row_id, templates in rows:
        if not templates:
            continue
        rewritten = _rewrite(str(templates), reverse=reverse)
        if rewritten is None:
            continue
        bind.execute(
            sa.text("UPDATE MESSAGE_CLIENT SET TEMPLATES = :templates WHERE ID = :id"),
            {"templates": rewritten, "id": row_id},
        )


def upgrade() -> None:
    _refresh()


def downgrade() -> None:
    _refresh(reverse=True)
