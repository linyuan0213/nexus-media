"""
媒体信息 Repository 适配器
将 MediaInfoRepository 适配为统一接口
"""

from app.db.repositories.media_repository import MediaInfoRepository, MediaRecord


class MediaInfoRepositoryAdapter:
    """媒体信息仓储适配器"""

    def __init__(self, repo: MediaInfoRepository | None = None):
        self._repo = repo or MediaInfoRepository()

    def get_by_path(self, path: str) -> MediaRecord | None:
        return self._repo.get_by_download_path(path)

    def get_by_title(self, name: str) -> MediaRecord | None:
        return self._repo.get_by_torrent_name(name)

    # 兼容旧 Repository 方法名
    def get_by_download_path(self, path: str) -> MediaRecord | None:
        return self._repo.get_by_download_path(path)

    def get_by_torrent_name(self, name: str) -> MediaRecord | None:
        return self._repo.get_by_torrent_name(name)
