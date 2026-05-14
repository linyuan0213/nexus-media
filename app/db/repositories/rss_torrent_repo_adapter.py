"""
RSS 种子领域 Repository 适配器
"""

from app.db.repositories.rss_repository import RssRepository
from app.domain.entities.rss_torrent import RssTorrentEntity
from app.domain.interfaces.rss_torrent_repo import IRssTorrentRepository


class RssTorrentRepositoryAdapter(IRssTorrentRepository):
    """RSS 种子仓储适配器"""

    def __init__(self, repo: RssRepository | None = None):
        self._repo = repo or RssRepository()

    def get_by_enclosure(self, enclosure: str) -> RssTorrentEntity | None:
        row = self._repo.get_rss_torrent_by_enclosure(enclosure)
        return RssTorrentEntity.from_orm(row)

    def get_by_name(self, torrent_name: str) -> RssTorrentEntity | None:
        row = self._repo.get_rss_torrent_by_name(torrent_name)
        return RssTorrentEntity.from_orm(row)

    def insert(self, torrent_name: str, enclosure: str, type_: str, title: str,
               year: str, season: str, episode: str) -> bool:
        self._repo.insert_rss_torrent(torrent_name, enclosure, type_, title, year, season, episode)
        return True

    def simple_insert(self, title: str, enclosure: str) -> bool:
        self._repo.simple_insert_rss_torrent(title, enclosure)
        return True

    def simple_delete(self, title: str, enclosure: str | None = None) -> bool:
        self._repo.simple_delete_rss_torrent(title, enclosure)
        return True

    def truncate(self) -> bool:
        self._repo.truncate_rss_torrents()
        return True

    def is_exists_by_enclosure(self, enclosure: str) -> bool:
        return self._repo.get_rss_torrent_by_enclosure(enclosure) is not None

    def is_exists_by_name(self, torrent_name: str, enclosure: str | None = None) -> bool:
        if enclosure:
            return self._repo.get_rss_torrent_by_enclosure(enclosure) is not None
        return self._repo.get_rss_torrent_by_name(torrent_name) is not None
