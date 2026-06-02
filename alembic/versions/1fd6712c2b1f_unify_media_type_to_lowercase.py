"""unify_media_type_to_lowercase

Revision ID: 1fd6712c2b1f
Revises: f8a9b0c1d2e3
Create Date: 2026-06-01 18:39:25.232419

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "1fd6712c2b1f"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


# 媒体类型映射：旧值 -> 新值
MEDIA_TYPE_MAP = {
    "电影": "movie",
    "MOVIE": "movie",
    "MOV": "movie",
    "剧集": "tv",
    "电视剧": "tv",
    "TV": "tv",
    "动漫": "anime",
    "ANIME": "anime",
    "ANI": "anime",
    "未知": "unknown",
}


def _update_table_type(table: str, column: str = "TYPE") -> None:
    """更新指定表的媒体类型字段"""
    for old, new in MEDIA_TYPE_MAP.items():
        op.execute(f"UPDATE {table} SET {column} = '{new}' WHERE {column} = '{old}'")


def upgrade() -> None:
    _update_table_type("DOWNLOAD_HISTORY")
    _update_table_type("SUBSCRIBE_HISTORY")
    _update_table_type("SUBSCRIBE_TORRENTS")
    _update_table_type("SEARCH_RESULT_INFO")
    _update_table_type("TRANSFER_HISTORY")
    _update_table_type("TMDB_BLACKLIST", "MEDIA_TYPE")
    _update_table_type("MEDIASYNC_ITEMS", "ITEM_TYPE")


def downgrade() -> None:
    reverse_map = {v: k for k, v in MEDIA_TYPE_MAP.items()}
    for new, old in reverse_map.items():
        op.execute(f"UPDATE DOWNLOAD_HISTORY SET TYPE = '{old}' WHERE TYPE = '{new}'")
        op.execute(f"UPDATE SUBSCRIBE_HISTORY SET TYPE = '{old}' WHERE TYPE = '{new}'")
        op.execute(f"UPDATE SUBSCRIBE_TORRENTS SET TYPE = '{old}' WHERE TYPE = '{new}'")
        op.execute(f"UPDATE SEARCH_RESULT_INFO SET TYPE = '{old}' WHERE TYPE = '{new}'")
        op.execute(f"UPDATE TRANSFER_HISTORY SET TYPE = '{old}' WHERE TYPE = '{new}'")
        op.execute(f"UPDATE TMDB_BLACKLIST SET MEDIA_TYPE = '{old}' WHERE MEDIA_TYPE = '{new}'")
        op.execute(f"UPDATE MEDIASYNC_ITEMS SET ITEM_TYPE = '{old}' WHERE ITEM_TYPE = '{new}'")
