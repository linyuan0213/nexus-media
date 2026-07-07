"""
RSS领域 Repository 适配器
将旧版 SubscribeRepository 适配为新领域接口
"""

from app.db.repositories.subscribe_repository import SubscribeRepository
from app.domain.entities.rss import (
    SubscribeHistoryEntity,
    SubscribeMovieEntity,
    SubscribeState,
    SubscribeTvEntity,
)
from app.domain.mediatypes import MediaType


class SubscribeMovieRepositoryAdapter:
    """RSS电影订阅仓储适配器"""

    def __init__(self, repo: SubscribeRepository | None = None):
        self._repo = repo or SubscribeRepository()

    def get_all(self, state: str | None = None, rssid: int | None = None) -> list[SubscribeMovieEntity]:
        rows = self._repo.get_rss_movies(state=state, rssid=rssid)
        if not rows:
            return []
        return [entity for entity in [SubscribeMovieEntity.from_orm(r) for r in rows] if entity is not None]

    def get_id(self, title: str, year: str | None = None, tmdbid: str | None = None) -> str | int | None:
        return self._repo.get_rss_movie_id(title, year, tmdbid)

    def is_exists(self, title: str, year: str) -> bool:
        return self._repo.is_exists_rss_movie(title, year)

    def update_tmdb(self, rid: int, tmdbid: str, title: str, year: str, image: str, desc: str, note: str) -> None:
        self._repo.update_rss_movie_tmdb(rid, tmdbid, title, year, image, desc, note)

    def update_desc(self, rid: int, desc: str) -> None:
        self._repo.update_rss_movie_desc(rid, desc)

    def update_state(self, title: str | None, year: str | None, rssid: int | None, state: str) -> None:
        self._repo.update_rss_movie_state(title, year, rssid, state)

    # 兼容旧Repository方法名
    def update_subscribe_movie_state(
        self,
        title=None,
        year=None,
        rssid=None,
        state=SubscribeState.RUNNING.value,
    ) -> None:
        self.update_state(title, year, rssid, state)

    def update(self, rssid: int, **kwargs) -> int:
        return self._repo.update_rss_movie(rssid, **kwargs)

    def update_filter_order(self, rssid: int, res_order: int) -> None:

        self._repo.update_rss_filter_order(MediaType.MOVIE.value, rssid, str(res_order))

    def get_filter_order(self, rssid: int) -> int:

        return self._repo.get_rss_overedition_order(MediaType.MOVIE.value, rssid)

    # 兼容旧Repository方法名
    def get_rss_overedition_order(self, rtype, rssid) -> int:
        return self.get_filter_order(rssid)

    def delete(
        self, title: str | None = None, year: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        self._repo.delete_rss_movie(title, year, rssid, tmdbid)

    def insert(
        self,
        media_info,
        state=SubscribeState.PENDING.value,
        rss_sites=None,
        search_sites=None,
        over_edition=0,
        filter_restype=None,
        filter_pix=None,
        filter_team=None,
        filter_rule=None,
        filter_include=None,
        filter_exclude=None,
        filter_free=None,
        save_path=None,
        download_setting: int | None = -1,
        fuzzy_match=0,
        desc=None,
        note=None,
        keyword=None,
    ) -> int:
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
            filter_free=filter_free,
            save_path=save_path,
            download_setting=download_setting if download_setting is not None else -1,
            fuzzy_match=fuzzy_match,
            desc=desc,
            note=note,
            keyword=keyword,
        )


class SubscribeTvRepositoryAdapter:
    """RSS剧集订阅仓储适配器"""

    def __init__(self, repo: SubscribeRepository | None = None):
        self._repo = repo or SubscribeRepository()

    def get_all(self, state: str | None = None, rssid: int | None = None) -> list[SubscribeTvEntity]:
        rows = self._repo.get_rss_tvs(state=state, rssid=rssid)
        if not rows:
            return []
        return [entity for entity in [SubscribeTvEntity.from_orm(r) for r in rows] if entity is not None]

    def get_id(
        self, title: str, year: str | None = None, season: str | None = None, tmdbid: str | None = None
    ) -> int | str | None:
        return self._repo.get_rss_tv_id(title, year, season, tmdbid)

    def is_exists(self, title: str, year: str, season: str | None = None) -> bool:
        return self._repo.is_exists_rss_tv(title, year, season)

    def update_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, total: int, lack: int, image: str, desc: str, note: str
    ) -> None:
        self._repo.update_rss_tv_tmdb(rid, tmdbid, title, year, total, lack, image, desc, note)

    def update_desc(self, rid: int, desc: str) -> None:
        self._repo.update_rss_tv_desc(rid, desc)

    def update_state(
        self, title: str | None, year: str | None, season: str | None, rssid: int | None, state: str
    ) -> None:
        self._repo.update_rss_tv_state(title, year, season, rssid, state)

    # 兼容旧Repository方法名
    def update_subscribe_tv_state(
        self,
        title=None,
        year=None,
        season=None,
        rssid=None,
        state=SubscribeState.RUNNING.value,
    ) -> None:
        self.update_state(title, year, season, rssid, state)

    def update_lack(
        self,
        title: str | None,
        year: str | None,
        season: str | None,
        rssid: int | None,
        lack_episodes: list[int] | None,
    ) -> None:
        self._repo.update_rss_tv_lack(title, year, season, rssid, lack_episodes if lack_episodes is not None else [])

    def update_filter_order(self, rssid: int, res_order: int) -> None:

        self._repo.update_rss_filter_order(MediaType.TV.value, rssid, str(res_order))

    def get_filter_order(self, rssid: int) -> int:

        return self._repo.get_rss_overedition_order(MediaType.TV.value, rssid)

    def delete(
        self, title: str | None = None, season: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        self._repo.delete_rss_tv(title, season, rssid, tmdbid)

    def update(self, rssid: int, **kwargs) -> int:
        return self._repo.update_rss_tv(rssid, **kwargs)

    def insert(
        self,
        media_info,
        total,
        lack=0,
        state=SubscribeState.PENDING.value,
        rss_sites=None,
        search_sites=None,
        over_edition=0,
        filter_restype=None,
        filter_pix=None,
        filter_team=None,
        filter_rule=None,
        filter_include=None,
        filter_exclude=None,
        filter_free=None,
        save_path=None,
        download_setting: int | None = -1,
        total_ep=None,
        current_ep=None,
        fuzzy_match=0,
        desc=None,
        note=None,
        keyword=None,
    ) -> int:
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
            filter_free=filter_free,
            save_path=save_path,
            download_setting=download_setting if download_setting is not None else -1,
            total_ep=total_ep,
            current_ep=current_ep,
            fuzzy_match=fuzzy_match,
            desc=desc,
            note=note,
            keyword=keyword,
        )


class SubscribeTvEpisodeRepositoryAdapter:
    """RSS剧集分集仓储适配器"""

    def __init__(self, repo: SubscribeRepository | None = None):
        self._repo = repo or SubscribeRepository()

    # 兼容旧Repository方法名
    def update_rss_tv_episodes(self, rid, episodes) -> None:
        self.update(rid, episodes)

    # 兼容旧Repository方法名
    def get_rss_tv_episodes(self, rid: int) -> list[int] | None:
        return self.get(rid)

    def is_exists(self, rid: int) -> bool:
        return self._repo.is_exists_rss_tv_episodes(rid)

    def update(self, rid: int, episodes: list[int]) -> None:
        self._repo.update_rss_tv_episodes(rid, episodes)

    def get(self, rid: int) -> list[int] | None:
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


class SubscribeHistoryRepositoryAdapter:
    """RSS历史仓储适配器"""

    def __init__(self, repo: SubscribeRepository | None = None):
        self._repo = repo or SubscribeRepository()

    # 兼容旧Repository方法名
    def insert_rss_history(
        self, rssid, rtype, name, year, tmdbid, image, desc, season=None, total=None, start=None, note=""
    ) -> None:
        self.insert(rssid, rtype, name, year, tmdbid, image, desc, season, total, start, note)

    # 兼容旧Repository方法名
    def check_rss_history(self, type_str, name, year, season) -> bool:
        return self.check_exists(type_str, name, year, season)

    def get_rss_history(self, rtype=None, rid=None):
        return self.get_all(rtype, rid)

    def delete_rss_history(self, rssid):
        self.delete(rssid)

    def get_all(self, rtype: str | None = None, rid: int | None = None) -> list[SubscribeHistoryEntity]:
        rows = self._repo.get_rss_history(rtype=rtype, rid=rid)
        if not rows:
            return []
        return [entity for entity in [SubscribeHistoryEntity.from_orm(r) for r in rows] if entity is not None]

    def is_exists(self, rssid: int | None) -> bool:
        if rssid is None:
            return False
        return self._repo.is_exists_rss_history(rssid)

    def check_exists(self, type_str: str, name: str, year: str, season: str) -> bool:
        return self._repo.check_rss_history(type_str, name, year, season)

    def insert(
        self,
        rssid: int,
        rtype: str,
        name: str,
        year: str,
        tmdbid: str,
        image: str,
        desc: str,
        season: str | None = None,
        total: int | None = None,
        start: int | None = None,
        note: str = "",
    ) -> None:
        self._repo.insert_rss_history(
            rssid,
            rtype,
            name,
            year,
            tmdbid,
            image,
            desc,
            season,
            str(total) if total is not None else None,
            str(start) if start is not None else None,
            note,
        )

    def upsert(
        self,
        rssid: int,
        rtype: str,
        name: str,
        year: str,
        tmdbid: str,
        image: str,
        desc: str,
        season: str | None = None,
        total: int | None = None,
        start: int | None = None,
        note: str = "",
    ) -> None:
        self._repo.upsert_rss_history(
            rssid,
            rtype,
            name,
            year,
            tmdbid,
            image,
            desc,
            season,
            str(total) if total is not None else None,
            str(start) if start is not None else None,
            note,
        )

    def delete(self, rssid: int | None) -> None:
        if rssid is None:
            return
        self._repo.delete_rss_history(rssid)
