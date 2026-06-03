from dataclasses import dataclass

from app.db.repositories.download_repo_adapter import DownloadHistoryRepositoryAdapter
from app.domain.mediatypes import MediaType
from app.di import container


@dataclass
class MediaRecord:
    """已识别媒体记录"""

    tmdbid: str
    type: MediaType
    title: str = ""
    year: str = ""
    season: int | None = None
    episode: int | None = None


class MediaInfoRepository:
    """媒体信息仓储 — 从数据库查已识别的媒体记录"""

    def __init__(self, download_repo: DownloadHistoryRepositoryAdapter | None = None):
        self._download_repo = download_repo or container.download_history_repo()

    def get_by_download_path(self, path: str) -> MediaRecord | None:
        """根据下载路径查下载历史"""
        row = self._download_repo.get_by_path(path)
        if not row:
            return None
        return self._to_record(row)

    def get_by_torrent_name(self, name: str) -> MediaRecord | None:
        """根据种子名称查下载历史"""
        rows = self._download_repo.get_by_title(name)
        if not rows:
            return None
        return self._to_record(rows[0])

    @staticmethod
    def _to_record(entity) -> MediaRecord | None:
        if not entity or not entity.tmdb_id:
            return None
        mtype = MediaType.MOVIE if entity.type == MediaType.MOVIE.value else MediaType.TV
        return MediaRecord(
            tmdbid=str(entity.tmdb_id),
            type=mtype,
            title=entity.title or "",
            year=str(entity.year) if entity.year else "",
        )
