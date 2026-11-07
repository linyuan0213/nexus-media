"""series alias season key

Revision ID: 3a6abdf71b57
Revises: 9217b6230331
Create Date: 2026-11-05 13:32:14.928480

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "3a6abdf71b57"
down_revision = "9217b6230331"
branch_labels = None
depends_on = None

_ALIAS_COLUMNS = (
    "PROVIDER",
    "EXTERNAL_ID",
    "SCOPE",
    "SEASON_NUMBER",
    "SERIES_KEY",
    "CONFIDENCE",
    "MAPPING_SOURCE",
    "CREATED_AT",
)


def _quote(name: str) -> str:
    """PostgreSQL 会把未加引号的标识符折叠为小写，必须显式引用大写表名/列名。"""
    return op.get_bind().dialect.identifier_preparer.quote(name)


def _copy_aliases(columns: tuple[str, ...] = _ALIAS_COLUMNS) -> None:
    names = ", ".join(_quote(column) for column in columns)
    op.execute(
        f"INSERT INTO {_quote('MEDIA_SERIES_ALIAS')} ({names}) "
        f"SELECT {names} FROM {_quote('MEDIA_SERIES_ALIAS_OLD')}"
    )


def _release_old_names(table_name: str) -> None:
    """旧表改名后仍占用索引/约束名，重建同名对象前必须先释放。"""
    inspector = sa.inspect(op.get_bind())
    if "ix_MEDIA_SERIES_ALIAS_SERIES_KEY" in {item["name"] for item in inspector.get_indexes(table_name)}:
        op.drop_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", table_name=table_name)
    if op.get_bind().dialect.name != "postgresql":
        return
    # PostgreSQL 的索引名在 schema 内全局唯一，主键/唯一约束各占一个索引名。
    pk_name = inspector.get_pk_constraint(table_name).get("name")
    if pk_name:
        op.drop_constraint(pk_name, table_name, type_="primary")
    for constraint in inspector.get_unique_constraints(table_name):
        name = constraint.get("name")
        if name:
            op.drop_constraint(name, table_name, type_="unique")


def upgrade() -> None:
    op.rename_table("MEDIA_SERIES_ALIAS", "MEDIA_SERIES_ALIAS_OLD")
    _release_old_names("MEDIA_SERIES_ALIAS_OLD")
    op.create_table(
        "MEDIA_SERIES_ALIAS",
        sa.Column("PROVIDER", sa.String(length=64), nullable=False),
        sa.Column("EXTERNAL_ID", sa.String(length=255), nullable=False),
        sa.Column("SCOPE", sa.String(length=64), nullable=False),
        sa.Column("SEASON_NUMBER", sa.Integer(), nullable=False),
        sa.Column("SERIES_KEY", sa.String(length=64), nullable=False),
        sa.Column("CONFIDENCE", sa.Integer(), nullable=False),
        sa.Column("MAPPING_SOURCE", sa.String(length=32), nullable=False),
        sa.Column("CREATED_AT", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE", "SEASON_NUMBER"),
    )
    op.create_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", "MEDIA_SERIES_ALIAS", ["SERIES_KEY"])
    _copy_aliases()
    op.drop_table("MEDIA_SERIES_ALIAS_OLD")


def downgrade() -> None:
    op.rename_table("MEDIA_SERIES_ALIAS", "MEDIA_SERIES_ALIAS_OLD")
    _release_old_names("MEDIA_SERIES_ALIAS_OLD")
    op.create_table(
        "MEDIA_SERIES_ALIAS",
        sa.Column("PROVIDER", sa.String(length=64), nullable=False),
        sa.Column("EXTERNAL_ID", sa.String(length=255), nullable=False),
        sa.Column("SCOPE", sa.String(length=64), nullable=False),
        sa.Column("SEASON_NUMBER", sa.Integer(), nullable=False),
        sa.Column("SERIES_KEY", sa.String(length=64), nullable=False),
        sa.Column("CONFIDENCE", sa.Integer(), nullable=False),
        sa.Column("MAPPING_SOURCE", sa.String(length=32), nullable=False),
        sa.Column("CREATED_AT", sa.String(length=20), nullable=True),
        sa.PrimaryKeyConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE"),
        sa.UniqueConstraint("PROVIDER", "EXTERNAL_ID", "SCOPE", name="uq_series_alias_provider_ref"),
    )
    op.create_index("ix_MEDIA_SERIES_ALIAS_SERIES_KEY", "MEDIA_SERIES_ALIAS", ["SERIES_KEY"])
    _copy_aliases()
    op.drop_table("MEDIA_SERIES_ALIAS_OLD")
