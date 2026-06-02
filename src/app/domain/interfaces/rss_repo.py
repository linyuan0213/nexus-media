"""
订阅领域 Repository 接口（Python Protocol）
定义 SubscribeMovie/SubscribeTv/SubscribeHistory 的仓储契约
"""

from typing import Protocol

from app.domain.entities.rss import (
    SubscribeHistoryEntity,
    SubscribeMovieEntity,
    SubscribeTvEntity,
)


class ISubscribeMovieRepository(Protocol):
    """订阅电影仓储接口"""

    def get_all(self, state: str | None = None, rssid: int | None = None) -> list[SubscribeMovieEntity]:
        """查询订阅电影列表"""
        ...

    def get_id(self, title: str, year: str | None = None, tmdbid: str | None = None) -> str | int | None:
        """获取订阅电影ID"""
        ...

    def is_exists(self, title: str, year: str) -> bool:
        """判断订阅电影是否存在"""
        ...

    def update_tmdb(self, rid: int, tmdbid: str, title: str, year: str, image: str, desc: str, note: str) -> None:
        """更新TMDB信息"""
        ...

    def update_desc(self, rid: int, desc: str) -> None:
        """更新描述"""
        ...

    def update_state(self, title: str | None, year: str | None, rssid: int | None, state: str) -> None:
        """更新状态"""
        ...

    def update_filter_order(self, rssid: int, res_order: int) -> None:
        """更新过滤优先级"""
        ...

    def get_filter_order(self, rssid: int) -> int:
        """获取过滤优先级"""
        ...

    def insert(
        self,
        media_info,
        state="D",
        rss_sites=None,
        search_sites=None,
        over_edition=0,
        filter_restype=None,
        filter_pix=None,
        filter_team=None,
        filter_rule=None,
        filter_include=None,
        filter_exclude=None,
        save_path=None,
        download_setting: int | None = -1,
        fuzzy_match=0,
        desc=None,
        note=None,
        keyword=None,
    ) -> int:
        """插入订阅电影"""
        ...

    def delete(
        self, title: str | None = None, year: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        """删除订阅电影"""
        ...


class ISubscribeTvRepository(Protocol):
    """订阅剧集仓储接口"""

    def get_all(self, state: str | None = None, rssid: int | None = None) -> list[SubscribeTvEntity]:
        """查询订阅剧集列表"""
        ...

    def get_id(
        self, title: str, year: str | None = None, season: str | None = None, tmdbid: str | None = None
    ) -> str | int | None:
        """获取订阅剧集ID"""
        ...

    def is_exists(self, title: str, year: str, season: str | None = None) -> bool:
        """判断订阅剧集是否存在"""
        ...

    def update_tmdb(
        self, rid: int, tmdbid: str, title: str, year: str, total: int, lack: int, image: str, desc: str, note: str
    ) -> None:
        """更新TMDB信息"""
        ...

    def update_desc(self, rid: int, desc: str) -> None:
        """更新描述"""
        ...

    def update_filter_order(self, rssid: int, res_order: int) -> None:
        """更新过滤优先级"""
        ...

    def get_filter_order(self, rssid: int) -> int:
        """获取过滤优先级"""
        ...

    def update_state(
        self, title: str | None, year: str | None, season: str | None, rssid: int | None, state: str
    ) -> None:
        """更新状态"""
        ...

    def update_lack(
        self,
        title: str | None,
        year: str | None,
        season: str | None,
        rssid: int | None,
        lack_episodes: list[int] | None,
    ) -> None:
        """更新缺失集数"""
        ...

    def update(self, rssid: int, **kwargs) -> int:
        """更新订阅剧集字段（支持 current_ep, lack, state 等）"""
        ...

    def insert(
        self,
        media_info,
        total,
        lack=0,
        state="D",
        rss_sites=None,
        search_sites=None,
        over_edition=0,
        filter_restype=None,
        filter_pix=None,
        filter_team=None,
        filter_rule=None,
        filter_include=None,
        filter_exclude=None,
        save_path=None,
        download_setting: int | None = -1,
        total_ep=None,
        current_ep=None,
        fuzzy_match=0,
        desc=None,
        note=None,
        keyword=None,
    ) -> int:
        """插入订阅剧集"""
        ...

    def delete(
        self, title: str | None = None, season: str | None = None, rssid: int | None = None, tmdbid: str | None = None
    ) -> None:
        """删除订阅剧集"""
        ...


class ISubscribeTvEpisodeRepository(Protocol):
    """订阅剧集分集仓储接口"""

    def is_exists(self, rid: int) -> bool:
        """判断是否存在"""
        ...

    def update(self, rid: int, episodes: list[int]) -> None:
        """更新缺失剧集"""
        ...

    def get(self, rid: int) -> list[int] | None:
        """获取缺失剧集"""
        ...

    def delete(self, rid: int) -> None:
        """删除"""
        ...

    def delete_all(self) -> None:
        """清空全部"""
        ...


class ISubscribeHistoryRepository(Protocol):
    """订阅历史仓储接口"""

    def get_all(self, rtype: str | None = None, rid: int | None = None) -> list[SubscribeHistoryEntity]:
        """查询订阅历史"""
        ...

    def is_exists(self, rssid: str) -> bool:
        """判断是否存在"""
        ...

    def check_exists(self, type_str: str, name: str, year: str, season: str) -> bool:
        """检查是否存在"""
        ...

    def insert(
        self,
        rssid: str,
        rtype: str,
        name: str,
        year: str,
        tmdbid: str,
        image: str,
        desc: str,
        season: str | None = None,
        total: int | None = None,
        start: int | None = None,
    ) -> None:
        """插入历史"""
        ...

    def delete(self, rssid: str) -> None:
        """删除历史"""
        ...
