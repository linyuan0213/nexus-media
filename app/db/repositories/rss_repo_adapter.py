# -*- coding: utf-8 -*-
"""
RSS领域 Repository 适配器
将旧版 RssRepository 适配为新领域接口
"""
from typing import List, Optional

from app.domain.entities.rss import (
    RssHistoryEntity,
    RssMovieEntity,
    RssTvEntity,
    RssTvEpisodeEntity,
)
from app.db.repositories.rss_repository import RssRepository


class RssMovieRepositoryAdapter:
    """RSS电影订阅仓储适配器"""

    def __init__(self, repo: Optional[RssRepository] = None):
        self._repo = repo or RssRepository()

    def get_all(self, state: Optional[str] = None, rssid: Optional[int] = None) -> List[RssMovieEntity]:
        rows = self._repo.get_rss_movies(state=state, rssid=rssid)
        if not rows:
            return []
        return [entity for entity in [RssMovieEntity.from_orm(r) for r in rows] if entity is not None]

    def get_id(self, title: str, year: Optional[str] = None, tmdbid: Optional[str] = None) -> str:
        return self._repo.get_rss_movie_id(title, year, tmdbid)

    def is_exists(self, title: str, year: str) -> bool:
        return self._repo.is_exists_rss_movie(title, year)

    def update_tmdb(self, rid: int, tmdbid: str, title: str, year: str, image: str, desc: str, note: str) -> None:
        self._repo.update_rss_movie_tmdb(rid, tmdbid, title, year, image, desc, note)

    def update_desc(self, rid: int, desc: str) -> None:
        self._repo.update_rss_movie_desc(rid, desc)

    def update_state(self, title: Optional[str], year: Optional[str], rssid: Optional[int], state: str) -> None:
        self._repo.update_rss_movie_state(title, year, rssid, state)

    def update_filter_order(self, rssid: int, res_order: int) -> None:
        from app.utils.types import MediaType
        self._repo.update_rss_filter_order(MediaType.MOVIE, rssid, res_order)

    def get_filter_order(self, rssid: int) -> int:
        from app.utils.types import MediaType
        return self._repo.get_rss_overedition_order(MediaType.MOVIE, rssid)

    def delete(self, title: Optional[str] = None, year: Optional[str] = None, rssid: Optional[int] = None, tmdbid: Optional[str] = None) -> None:
        self._repo.delete_rss_movie(title, year, rssid, tmdbid)


class RssTvRepositoryAdapter:
    """RSS剧集订阅仓储适配器"""

    def __init__(self, repo: Optional[RssRepository] = None):
        self._repo = repo or RssRepository()

    def get_all(self, state: Optional[str] = None, rssid: Optional[int] = None) -> List[RssTvEntity]:
        rows = self._repo.get_rss_tvs(state=state, rssid=rssid)
        if not rows:
            return []
        return [entity for entity in [RssTvEntity.from_orm(r) for r in rows] if entity is not None]

    def get_id(self, title: str, year: Optional[str] = None, season: Optional[str] = None, tmdbid: Optional[str] = None) -> str:
        return self._repo.get_rss_tv_id(title, year, season, tmdbid)

    def is_exists(self, title: str, year: str, season: Optional[str] = None) -> bool:
        return self._repo.is_exists_rss_tv(title, year, season)

    def update_tmdb(self, rid: int, tmdbid: str, title: str, year: str, total: int, lack: int, image: str, desc: str, note: str) -> None:
        self._repo.update_rss_tv_tmdb(rid, tmdbid, title, year, total, lack, image, desc, note)

    def update_desc(self, rid: int, desc: str) -> None:
        self._repo.update_rss_tv_desc(rid, desc)

    def update_state(self, title: Optional[str], year: Optional[str], season: Optional[str], rssid: Optional[int], state: str) -> None:
        self._repo.update_rss_tv_state(title, year, season, rssid, state)

    def update_lack(self, title: Optional[str], year: Optional[str], season: Optional[str], rssid: Optional[int], lack_episodes: Optional[List[int]]) -> None:
        self._repo.update_rss_tv_lack(title, year, season, rssid, lack_episodes)

    def delete(self, title: Optional[str] = None, season: Optional[str] = None, rssid: Optional[int] = None, tmdbid: Optional[str] = None) -> None:
        self._repo.delete_rss_tv(title, season, rssid, tmdbid)


class RssTvEpisodeRepositoryAdapter:
    """RSS剧集分集仓储适配器"""

    def __init__(self, repo: Optional[RssRepository] = None):
        self._repo = repo or RssRepository()

    def is_exists(self, rid: int) -> bool:
        return self._repo.is_exists_rss_tv_episodes(rid)

    def update(self, rid: int, episodes: List[int]) -> None:
        self._repo.update_rss_tv_episodes(rid, episodes)

    def get(self, rid: int) -> Optional[List[int]]:
        return self._repo.get_rss_tv_episodes(rid)

    def delete(self, rid: int) -> None:
        self._repo.delete_rss_tv_episodes(rid)

    def delete_all(self) -> None:
        self._repo.truncate_rss_episodes()


class RssHistoryRepositoryAdapter:
    """RSS历史仓储适配器"""

    def __init__(self, repo: Optional[RssRepository] = None):
        self._repo = repo or RssRepository()

    def get_all(self, rtype: Optional[str] = None, rid: Optional[int] = None) -> List[RssHistoryEntity]:
        rows = self._repo.get_rss_history(rtype=rtype, rid=rid)
        if not rows:
            return []
        return [entity for entity in [RssHistoryEntity.from_orm(r) for r in rows] if entity is not None]

    def is_exists(self, rssid: str) -> bool:
        return self._repo.is_exists_rss_history(rssid)

    def check_exists(self, type_str: str, name: str, year: str, season: str) -> bool:
        return self._repo.check_rss_history(type_str, name, year, season)

    def insert(self, rssid: str, rtype: str, name: str, year: str, tmdbid: str,
               image: str, desc: str, season: Optional[str] = None, total: Optional[int] = None,
               start: Optional[int] = None) -> None:
        self._repo.insert_rss_history(rssid, rtype, name, year, tmdbid, image, desc, season, total, start)

    def delete(self, rssid: str) -> None:
        self._repo.delete_rss_history(rssid)
