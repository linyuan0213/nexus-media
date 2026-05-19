"""
媒体同步 Repository 适配器
将 MediaSyncRepository 适配为统一接口
"""

from app.db.repositories.media_sync_repository import MediaSyncRepository


class MediaSyncRepositoryAdapter:
    """媒体同步数据仓储适配器"""

    def __init__(self, repo: MediaSyncRepository | None = None):
        self._repo = repo or MediaSyncRepository()

    def insert(self, server_type: str | None, iteminfo: dict, seasoninfo: list | None = None) -> bool:
        if not server_type:
            return False
        return self._repo.insert_item(server_type, iteminfo, seasoninfo)

    def empty(self, server_type: str | None = None, library: str | None = None) -> bool:
        return self._repo.empty_items(server_type, library)

    def statistics(self, server_type: str | None, total_count: int, movie_count: int, tv_count: int) -> bool:
        if not server_type:
            return False
        return self._repo.save_statistics(server_type, total_count, movie_count, tv_count)

    def query(self, server_type: str | None, title: str | None, year: str | None = None, tmdbid: str | None = None):
        if not server_type or not title:
            return None
        return self._repo.query_item(server_type, title, year, tmdbid)

    def get_statistics(self, server_type: str | None):
        if not server_type:
            return None
        return self._repo.get_statistics(server_type)
