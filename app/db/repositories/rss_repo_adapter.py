# -*- coding: utf-8 -*-
"""
RSS领域 Repository 适配器
将旧版 RssRepository 适配为新领域接口
"""
from typing import Any, List, Optional

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

    # 兼容旧Repository方法名
    def update_rss_movie_state(self, title=None, year=None, rssid=None, state='R') -> None:
        self.update_state(title, year, rssid, state)

    def update_filter_order(self, rssid: int, res_order: int) -> None:
        from app.utils.types import MediaType
        self._repo.update_rss_filter_order(MediaType.MOVIE, rssid, res_order)

    def get_filter_order(self, rssid: int) -> int:
        from app.utils.types import MediaType
        return self._repo.get_rss_overedition_order(MediaType.MOVIE, rssid)

    # 兼容旧Repository方法名
    def get_rss_overedition_order(self, rtype, rssid) -> int:
        return self.get_filter_order(rssid)

    def delete(self, title: Optional[str] = None, year: Optional[str] = None, rssid: Optional[int] = None, tmdbid: Optional[str] = None) -> None:
        self._repo.delete_rss_movie(title, year, rssid, tmdbid)

    def insert(self, media_info, state="D", rss_sites=None, search_sites=None, over_edition=0,
               filter_restype=None, filter_pix=None, filter_team=None, filter_rule=None,
               filter_include=None, filter_exclude=None, save_path=None, download_setting: Optional[int] = -1,
               fuzzy_match=0, desc=None, note=None, keyword=None) -> int:
        return self._repo.insert_rss_movie(
            media_info=media_info,
            state=state,
            rss_sites=rss_sites,
            search_sites=search_sites,
            over_edition=over_edition,
            filter_restype=filter_restype,
            filter_pix=filter_pix,
            filter_team=filter_team,
            filter_rule=filter_rule,
            filter_include=filter_include,
            filter_exclude=filter_exclude,
            save_path=save_path,
            download_setting=download_setting,
            fuzzy_match=fuzzy_match,
            desc=desc,
            note=note,
            keyword=keyword
        )


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

    # 兼容旧Repository方法名
    def update_rss_tv_state(self, title=None, year=None, season=None, rssid=None, state='R') -> None:
        self.update_state(title, year, season, rssid, state)

    def update_lack(self, title: Optional[str], year: Optional[str], season: Optional[str], rssid: Optional[int], lack_episodes: Optional[List[int]]) -> None:
        self._repo.update_rss_tv_lack(title, year, season, rssid, lack_episodes)

    def update_filter_order(self, rssid: int, res_order: int) -> None:
        from app.utils.types import MediaType
        self._repo.update_rss_filter_order(MediaType.TV, rssid, res_order)

    def get_filter_order(self, rssid: int) -> int:
        from app.utils.types import MediaType
        return self._repo.get_rss_overedition_order(MediaType.TV, rssid)

    def delete(self, title: Optional[str] = None, season: Optional[str] = None, rssid: Optional[int] = None, tmdbid: Optional[str] = None) -> None:
        self._repo.delete_rss_tv(title, season, rssid, tmdbid)

    def insert(self, media_info, total, lack=0, state="D", rss_sites=None, search_sites=None, over_edition=0,
               filter_restype=None, filter_pix=None, filter_team=None, filter_rule=None,
               filter_include=None, filter_exclude=None, save_path=None, download_setting: Optional[int] = -1,
               total_ep=None, current_ep=None, fuzzy_match=0, desc=None, note=None, keyword=None) -> int:
        return self._repo.insert_rss_tv(
            media_info=media_info,
            total=total,
            lack=lack,
            state=state,
            rss_sites=rss_sites,
            search_sites=search_sites,
            over_edition=over_edition,
            filter_restype=filter_restype,
            filter_pix=filter_pix,
            filter_team=filter_team,
            filter_rule=filter_rule,
            filter_include=filter_include,
            filter_exclude=filter_exclude,
            save_path=save_path,
            download_setting=download_setting,
            total_ep=total_ep,
            current_ep=current_ep,
            fuzzy_match=fuzzy_match,
            desc=desc,
            note=note,
            keyword=keyword
        )


class RssTvEpisodeRepositoryAdapter:
    """RSS剧集分集仓储适配器"""

    def __init__(self, repo: Optional[RssRepository] = None):
        self._repo = repo or RssRepository()

    # 兼容旧Repository方法名
    def update_rss_tv_episodes(self, rid, episodes) -> None:
        self.update(rid, episodes)

    # 兼容旧Repository方法名
    def get_rss_tv_episodes(self, rid: int) -> Optional[List[int]]:
        return self.get(rid)

    def is_exists(self, rid: int) -> bool:
        return self._repo.is_exists_rss_tv_episodes(rid)

    def update(self, rid: int, episodes: List[int]) -> None:
        self._repo.update_rss_tv_episodes(rid, episodes)

    def get(self, rid: int) -> Optional[List[int]]:
        return self._repo.get_rss_tv_episodes(rid)

    # 兼容旧Repository方法名
    def is_exists_rss_tv_episodes(self, rid: int) -> bool:
        return self.is_exists(rid)

    def delete(self, rid: int) -> None:
        self._repo.delete_rss_tv_episodes(rid)

    def delete_all(self) -> None:
        self._repo.truncate_rss_episodes()

    # 兼容旧Repository方法名
    def truncate_rss_episodes(self) -> None:
        self.delete_all()


class RssHistoryRepositoryAdapter:
    """RSS历史仓储适配器"""

    def __init__(self, repo: Optional[RssRepository] = None):
        self._repo = repo or RssRepository()

    # 兼容旧Repository方法名
    def insert_rss_history(self, rssid, rtype, name, year, tmdbid, image, desc, season=None, total=None, start=None) -> None:
        self.insert(rssid, rtype, name, year, tmdbid, image, desc, season, total, start)

    # 兼容旧Repository方法名
    def check_rss_history(self, type_str, name, year, season) -> bool:
        return self.check_exists(type_str, name, year, season)

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
