from dataclasses import dataclass
from typing import Any


@dataclass
class MediaInfoResultDTO:
    """媒体信息查询结果"""

    type: str = ""
    type_str: str = ""
    page: Any = None
    title: str = ""
    vote_average: float = 0.0
    poster_path: str = ""
    release_date: str = ""
    year: str = ""
    overview: str = ""
    link_url: str = ""
    tmdbid: Any = None
    rssid: Any = None
    seasons: list[dict] | None = None


@dataclass
class SeasonEpisodesResultDTO:
    """剧集查询结果"""

    episodes: list[dict] | None = None


@dataclass
class MediaSearchResultDTO:
    """搜索结果分组结果"""

    total: int = 0
    result: dict | None = None


@dataclass
class TransferHistoryPageDTO:
    """转移历史分页结果"""

    total: int = 0
    result: list[dict] | None = None
    total_page: int = 0
    page_num: int = 30
    current_page: int = 1


@dataclass
class UnknownListPageDTO:
    """未识别记录分页结果"""

    total: int = 0
    items: list[dict] | None = None
    total_page: int = 0
    page_num: int = 30
    current_page: int = 1


@dataclass
class LibrarySpaceDTO:
    """媒体库存储空间"""

    used_percent: float = 0.0
    free_space: str = ""
    used_space: str = ""
    total_space: str = ""


@dataclass
class TransferMediaDTO:
    """Repository 层使用的媒体信息 DTO，屏蔽对 MediaInfo 领域对象的直接依赖。"""

    title: str
    type_value: str
    category: str
    tmdb_id: int
    year: str
    season_episode: str
