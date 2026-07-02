"""add_foreign_keys_and_indexes

Revision ID: 77f7a8b9c0d1
Revises: 6d7e8f9a0b1c
Create Date: 2026-07-02 13:08:00

Add missing ForeignKey constraints and performance indexes.

ForeignKeys:
  - CONFIG_FILTER_RULES.GROUP_ID → CONFIG_FILTER_GROUP.ID
  - CONFIG_CATEGORY_RULE.CATEGORY_ID → CONFIG_CATEGORY.ID
  - CUSTOM_WORDS.GROUP_ID → CUSTOM_WORD_GROUPS.ID
  - API_KEY_LOGS.API_KEY_ID → API_KEYS.ID

Indexes:
  - DOWNLOADER (ENABLED, TYPE)
  - CONFIG_SYNC_PATHS (ENABLED)
  - SITE_BRUSH_TORRENTS (DOWNLOAD_ID)
  - SEARCH_RESULT_INFO (SEEDERS)
  - SITE_USER_INFO_STATS (USERNAME)
  - CUSTOM_WORDS (GROUP_ID)
"""

import sqlalchemy as sa

from alembic import op

revision = "77f7a8b9c0d1"
down_revision = "6d7e8f9a0b1c"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- ForeignKey constraints (only if table+column exist) ---
    _add_fk_if_columns(inspector, "CONFIG_FILTER_RULES", "GROUP_ID", "CONFIG_FILTER_GROUP", "ID")
    _add_fk_if_columns(inspector, "CONFIG_CATEGORY_RULE", "CATEGORY_ID", "CONFIG_CATEGORY", "ID")
    _add_fk_if_columns(inspector, "CUSTOM_WORDS", "GROUP_ID", "CUSTOM_WORD_GROUPS", "ID")
    _add_fk_if_columns(inspector, "API_KEY_LOGS", "API_KEY_ID", "API_KEYS", "ID")

    # --- Indexes (skip if already exist) ---
    _add_idx(inspector, "DOWNLOADER", "ENABLED")
    _add_idx(inspector, "DOWNLOADER", "TYPE")
    _add_idx(inspector, "CONFIG_SYNC_PATHS", "ENABLED")
    _add_idx(inspector, "SITE_BRUSH_TORRENTS", "DOWNLOAD_ID")
    _add_idx(inspector, "SEARCH_RESULT_INFO", "SEEDERS")
    _add_idx(inspector, "SITE_USER_INFO_STATS", "USERNAME")
    _add_idx(inspector, "CUSTOM_WORDS", "GROUP_ID")


def downgrade():
    # FK constraints
    _drop_fk_if_exists("CONFIG_FILTER_RULES", "GROUP_ID", "CONFIG_FILTER_GROUP")
    _drop_fk_if_exists("CONFIG_CATEGORY_RULE", "CATEGORY_ID", "CONFIG_CATEGORY")
    _drop_fk_if_exists("CUSTOM_WORDS", "GROUP_ID", "CUSTOM_WORD_GROUPS")
    _drop_fk_if_exists("API_KEY_LOGS", "API_KEY_ID", "API_KEYS")

    # Indexes
    _drop_idx("DOWNLOADER", "ENABLED")
    _drop_idx("DOWNLOADER", "TYPE")
    _drop_idx("CONFIG_SYNC_PATHS", "ENABLED")
    _drop_idx("SITE_BRUSH_TORRENTS", "DOWNLOAD_ID")
    _drop_idx("SEARCH_RESULT_INFO", "SEEDERS")
    _drop_idx("SITE_USER_INFO_STATS", "USERNAME")
    _drop_idx("CUSTOM_WORDS", "GROUP_ID")


def _add_fk_if_columns(inspector, table, column, ref_table, ref_column):
    if not inspector.has_table(table) or not inspector.has_table(ref_table):
        return
    cols = {c["name"] for c in inspector.get_columns(table)}
    ref_cols = {c["name"] for c in inspector.get_columns(ref_table)}
    if column not in cols or ref_column not in ref_cols:
        return
    existing_fks = {tuple(fk["constrained_columns"]) for fk in inspector.get_foreign_keys(table)}
    if (column,) in existing_fks:
        return
    fk_name = f"fk_{table}_{ref_table}_{column}"
    op.create_foreign_key(fk_name, table, ref_table, [column], [ref_column], source_schema=None, referent_schema=None)


def _drop_fk_if_exists(table, column, ref_table):
    try:
        bind = op.get_bind()
        inspector = sa.inspect(bind)
        if inspector.has_table(table):
            for fk in inspector.get_foreign_keys(table):
                fk_name = fk.get("name")
                if fk_name and fk.get("constrained_columns") == [column]:
                    op.drop_constraint(fk_name, table, type_="foreignkey")
                    return
    except Exception:
        pass


def _has_index(inspector, table, column):
    if not inspector.has_table(table):
        return True  # skip non-existent table
    for idx in inspector.get_indexes(table):
        if idx.get("column_names") == [column]:
            return True
    return False


def _add_idx(inspector, table, column):
    if not _has_index(inspector, table, column):
        idx_name = f"idx_{table}_{column}"
        op.create_index(idx_name, table, [column])


def _drop_idx(table, column):
    try:
        idx_name = f"idx_{table}_{column}"
        op.drop_index(idx_name, table_name=table)
    except Exception:
        pass
